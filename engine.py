"""Reward computation and recommendation logic (deterministic)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from cards import CreditCard
from models import RewardComputation, RewardRule, Transaction, UserProfile


def _normalize_category(category: str) -> str:
    return category.strip().lower()


def _transaction_date(transaction: Transaction) -> date | None:
    if transaction.timestamp:
        raw = transaction.timestamp.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None
    if transaction.txn_date is not None:
        return transaction.txn_date
    return None


def _rule_period_active(rule: RewardRule, d: date | None) -> bool:
    if d is None:
        return True
    window = rule.get("period")
    if isinstance(window, dict):
        start_s = window.get("start")
        end_s = window.get("end")
        if not start_s or not end_s:
            return True
        try:
            start = date.fromisoformat(str(start_s).strip()[:10])
            end = date.fromisoformat(str(end_s).strip()[:10])
        except ValueError:
            return True
        return start <= d <= end
    return True


def _rule_legacy_dates_active(rule: RewardRule, d: date | None) -> bool:
    if d is None:
        return True
    start = rule.get("start_date")
    end = rule.get("end_date")
    if start is not None and d < start:
        return False
    if end is not None and d > end:
        return False
    return True


def _transaction_field(transaction: Transaction, key: str) -> Any:
    if key == "channel":
        return transaction.channel
    if key == "booking_channel":
        return transaction.booking_channel
    meta = transaction.metadata or {}
    return meta.get(key)


def _conditions_satisfied(rule: RewardRule, transaction: Transaction) -> bool:
    cond = rule.get("conditions")
    if not cond:
        return True
    for key, expected in cond.items():
        if _transaction_field(transaction, str(key)) != expected:
            return False
    return True


def _exclusion_hits(rule: RewardRule, transaction: Transaction) -> bool:
    ex = rule.get("exclusions")
    if not ex:
        return False
    merchant_l = transaction.merchant.strip().lower()
    cat_l = _normalize_category(transaction.category)
    for raw in ex:
        token = str(raw).strip().lower()
        if not token:
            continue
        if token == cat_l:
            return True
        if token in merchant_l:
            return True
    return False


def _category_matches(rule: RewardRule, transaction: Transaction) -> bool:
    rtype = rule.get("type")
    if rtype == "universal_bonus":
        return True
    cat = rule.get("category")
    if cat is None:
        return False
    return _normalize_category(transaction.category) == _normalize_category(str(cat))


def _rule_matches(
    rule: RewardRule,
    transaction: Transaction,
    txn_day: date | None,
) -> bool:
    if not _category_matches(rule, transaction):
        return False
    if not _rule_period_active(rule, txn_day):
        return False
    if not _rule_legacy_dates_active(rule, txn_day):
        return False
    if not _conditions_satisfied(rule, transaction):
        return False
    if _exclusion_hits(rule, transaction):
        return False
    return True


def _rule_sort_key(rule: RewardRule) -> tuple[int, float]:
    pr = rule.get("priority")
    p = int(pr) if isinstance(pr, int) and not isinstance(pr, bool) else 0
    mult = float(rule.get("multiplier", 0))
    return (p, mult)


def _eligible_amount(
    card: CreditCard,
    rule_index: int,
    transaction: Transaction,
    rule: RewardRule,
    user_profile: UserProfile | None,
) -> float:
    amount = transaction.amount
    cap = rule.get("cap")
    if cap is None:
        return amount
    cap_f = float(cap)
    cap_period = rule.get("cap_period")
    spend_key = f"{card.name}#{rule_index}"
    already = 0.0
    if user_profile and cap_period:
        already = float(user_profile.per_rule_spend.get(spend_key, 0.0))
    if cap_period and user_profile:
        remaining = max(0.0, cap_f - already)
        return min(amount, remaining)
    return min(amount, cap_f)


def _period_suffix(rule: RewardRule) -> str:
    window = rule.get("period")
    if isinstance(window, dict):
        start = window.get("start")
        end = window.get("end")
        if start and end:
            return f" ({start}–{end})"
    if isinstance(window, str) and window:
        return f" ({window})"
    cp = rule.get("cap_period")
    if cp:
        return f" ({cp} cap)"
    return ""


def _explain_match(
    rule: RewardRule, transaction: Transaction, mult: float, eligible: float
) -> str:
    rtype = rule.get("type")
    cap_note = ""
    if eligible < transaction.amount - 1e-9:
        cap_note = f"; only ${eligible:.2f} qualifies (cap)"
    ps = _period_suffix(rule)

    if rtype == "category_bonus":
        cat = rule.get("category", transaction.category)
        return f"{mult:g}x on {_normalize_category(str(cat))} category{ps}{cap_note}"
    if rtype == "rotating_category":
        cat = rule.get("category", transaction.category)
        return f"{mult:g}x rotating on {_normalize_category(str(cat))}{ps}{cap_note}"
    if rtype == "relationship_bonus":
        cat = rule.get("category", transaction.category)
        return f"{mult:g}x relationship bonus on {_normalize_category(str(cat))}{ps}{cap_note}"
    if rtype == "universal_bonus":
        return f"{mult:g}x on all purchases{ps}{cap_note}"
    return f"{mult:g}x multiplier applied{cap_note}"


def compute_reward(
    card: CreditCard,
    transaction: Transaction,
    user_profile: UserProfile | None = None,
) -> RewardComputation:
    """
    Pick the highest-scoring matching rule by (priority, multiplier), then apply cap.

    If a rule has ``cap`` and ``cap_period`` and ``user_profile`` is provided, remaining
    cap room uses ``per_rule_spend["{cardName}#{ruleIndex}"]``; otherwise ``cap`` clips
    this transaction amount only.
    """
    if transaction.amount < 0:
        raise ValueError("transaction amount must be non-negative")

    txn_day = _transaction_date(transaction)
    candidates: list[tuple[int, RewardRule]] = [
        (i, r) for i, r in enumerate(card.reward_rules) if _rule_matches(r, transaction, txn_day)
    ]
    if not candidates:
        pts = transaction.amount * card.base_rate
        expl = (
            f"{card.base_rate:g}x base rate (no bonus rule matched)"
            if card.base_rate != 0
            else "no earn (base rate is 0)"
        )
        return RewardComputation(
            value_dollars=pts * card.point_value,
            points=pts,
            explanation=expl,
        )

    candidates.sort(key=lambda ir: _rule_sort_key(ir[1]), reverse=True)
    best_i, best_rule = candidates[0]
    mult = float(best_rule.get("multiplier", 0))
    if mult <= 0:
        pts = transaction.amount * card.base_rate
        return RewardComputation(
            value_dollars=pts * card.point_value,
            points=pts,
            explanation=f"{card.base_rate:g}x base rate (invalid winning rule multiplier)",
        )

    eligible = _eligible_amount(card, best_i, transaction, best_rule, user_profile)
    points = eligible * mult
    explanation = _explain_match(best_rule, transaction, mult, eligible)

    return RewardComputation(
        value_dollars=points * card.point_value,
        points=points,
        explanation=explanation,
    )


@dataclass(frozen=True)
class BestCardResult:
    card_name: str
    reward_value_dollars: float
    points: float
    explanation: str


def get_best_card(
    transaction: Transaction,
    cards: list[CreditCard],
    user_profile: UserProfile | None = None,
) -> BestCardResult:
    if not cards:
        raise ValueError("cards list must not be empty")

    best: BestCardResult | None = None
    for card in cards:
        comp = compute_reward(card, transaction, user_profile)
        if best is None or comp.value_dollars > best.reward_value_dollars:
            best = BestCardResult(
                card_name=card.name,
                reward_value_dollars=comp.value_dollars,
                points=comp.points,
                explanation=comp.explanation,
            )
    assert best is not None
    return best
