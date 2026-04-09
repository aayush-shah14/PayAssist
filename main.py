"""CLI entry point for the Credit Card Reward Optimizer."""

from __future__ import annotations

from engine import compute_reward, get_best_card
from models import Transaction
from policy import apply_policy
from storage import load_cards


def _prompt_float(label: str) -> float:
    raw = input(f"{label}: ").strip()
    return float(raw)


def main() -> None:
    print("Credit Card Reward Optimizer")
    print("Enter transaction details (blank merchant is ok).\n")

    merchant = input("Merchant: ").strip()
    category = input("Category: ").strip()
    amount = _prompt_float("Amount")

    cards = load_cards()
    transaction = Transaction(merchant=merchant, category=category, amount=amount)

    best = get_best_card(transaction, cards)
    final_name = apply_policy(best, transaction, cards)

    final_card = next(c for c in cards if c.name == final_name)
    final_comp = compute_reward(final_card, transaction)

    pts = final_comp.points
    pts_display = f"{pts:g}" if pts == int(pts) else f"{pts:.2f}"

    print()
    print(f"Recommended Card: {final_name}")
    print(f"Reason: {final_comp.explanation}")
    print(f"Estimated Reward: {pts_display} points (~${final_comp.value_dollars:.2f})")
    if final_name != best.card_name:
        print(
            f"(Pure reward maximization would suggest: {best.card_name} "
            f"~${best.reward_value_dollars:.2f})"
        )


if __name__ == "__main__":
    main()
