"""Reward computation and recommendation logic (deterministic)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from cards import CreditCard
from models import RewardComputation, RewardRule, Transaction


def _normalize_category(category: str) -> str:
    return category.strip().lower()


def _rule_active_on(rule: RewardRule, txn_date: date | None) -> bool:
    if txn_date is None:
        return True
    start = rule.get("start_date")
    end = rule.get("end_date")
    if start is not None and txn_date < start:
        return False
    if end is not None and txn_date > end:
        return False
    return True


def _conditions_satisfied(rule: RewardRule, transaction: Transaction) -> bool:
    cond = rule.get("conditions")
    if not cond:
        return True
    meta = transaction.metadata or {}
    for key, expected in cond.items():
        if meta.get(key) != expected:
            return False
    return True


def _rule_matches(rule: RewardRule, transaction: Transaction) -> bool:
    if not _rule_active_on(rule, transaction.txn_date):
        return False
    if not _conditions_satisfied(rule, transaction):
        return False

    rtype = rule.get("type")
    if rtype in ("category_bonus", "rotating_category"):
        cat = rule.get("category")
        if cat is None:
            return False
        return _normalize_category(transaction.category) == _normalize_category(str(cat))
    if rtype == "relationship_bonus":
        cat = rule.get("category")
        if cat is None:
            return False
        if _normalize_category(transaction.category) != _normalize_category(str(cat)):
            return False
        return True
    if rtype == "universal_bonus":
        return True
    return False


def _eligible_amount(transaction: Transaction, rule: RewardRule) -> float:
    cap = rule.get("cap")
    if cap is None:
        return transaction.amount
    return min(transaction.amount, float(cap))


def _period_suffix(rule: RewardRule) -> str:
    period = rule.get("period")
    if period:
        return f" ({period})"
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


def compute_reward(card: CreditCard, transaction: Transaction) -> RewardComputation:
    if transaction.amount < 0:
        raise ValueError("transaction amount must be non-negative")

    best_points = -1.0
    best_explanation = ""

    for rule in card.reward_rules:
        if not _rule_matches(rule, transaction):
            continue
        mult = float(rule.get("multiplier", 0))
        if mult <= 0:
            continue
        eligible = _eligible_amount(transaction, rule)
        points = eligible * mult
        if points > best_points:
            best_points = points
            best_explanation = _explain_match(rule, transaction, mult, eligible)

    if best_points < 0:
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

    return RewardComputation(
        value_dollars=best_points * card.point_value,
        points=best_points,
        explanation=best_explanation,
    )


@dataclass(frozen=True)
class BestCardResult:
    card_name: str
    reward_value_dollars: float
    points: float
    explanation: str


def get_best_card(transaction: Transaction, cards: list[CreditCard]) -> BestCardResult:
    if not cards:
        raise ValueError("cards list must not be empty")

    best: BestCardResult | None = None
    for card in cards:
        comp = compute_reward(card, transaction)
        if best is None or comp.value_dollars > best.reward_value_dollars:
            best = BestCardResult(
                card_name=card.name,
                reward_value_dollars=comp.value_dollars,
                points=comp.points,
                explanation=comp.explanation,
            )
    assert best is not None
    return best
