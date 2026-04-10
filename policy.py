"""Non-reward policy layer: preferences, score overrides, future seasonal/relationship hooks."""

from __future__ import annotations

from engine import BestCardResult, compute_reward
from cards import CreditCard
from models import Transaction, UserProfile

# Dollar amount added to deterministic reward value for tie-breaking / soft preferences.
SCORE_OVERRIDES: dict[str, float] = {
    "Amex Gold": 10.0,
}


def _find_bilt_card(cards: list[CreditCard]) -> CreditCard | None:
    for card in cards:
        if "bilt" in card.name.lower():
            return card
    return None


def _policy_score(
    card: CreditCard,
    transaction: Transaction,
    overrides: dict[str, float],
    user_profile: UserProfile | None,
) -> float:
    comp = compute_reward(card, transaction, user_profile)
    bonus = float(overrides.get(card.name, 0.0))
    return comp.value_dollars + bonus


def apply_policy(
    best_card: BestCardResult,
    transaction: Transaction,
    cards: list[CreditCard],
    *,
    score_overrides: dict[str, float] | None = None,
    user_profile: UserProfile | None = None,
) -> str:
    """
    Return the final recommended card name after applying policy on top of pure rewards.

    `best_card` is the raw reward winner from ``get_best_card`` (kept for API symmetry
    and future diagnostics); selection here re-scores all cards when overrides apply.

    Rules (initial):
    1. Rent: prefer a Bilt-named card when present in the wallet.
    2. Otherwise: pick the card with highest (reward dollars + SCORE_OVERRIDES[name]).

    Future: seasonal boosts / relationship bonuses can read transaction.metadata and
    adjust scores in this function without changing the LLM or core earn math.
    """
    _ = best_card  # reserved for logging / UI comparison vs pure reward winner
    overrides = SCORE_OVERRIDES if score_overrides is None else score_overrides

    if _normalize(transaction.category) == "rent":
        bilt = _find_bilt_card(cards)
        if bilt is not None:
            return bilt.name

    best_name = cards[0].name
    best_score = float("-inf")
    for card in cards:
        score = _policy_score(card, transaction, overrides, user_profile)
        if score > best_score:
            best_score = score
            best_name = card.name
    return best_name


def _normalize(category: str) -> str:
    return category.strip().lower()
