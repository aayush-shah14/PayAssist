"""Load and save credit cards from cards.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cards import CreditCard
from models import RewardRule
from validation import validate_card, validate_cards_file_payload

DEFAULT_CARDS_PATH = Path(__file__).resolve().parent / "cards.json"


def card_from_dict(raw: dict[str, Any]) -> CreditCard:
    rules: list[RewardRule] = list(raw.get("rules", []))
    return CreditCard(
        name=str(raw["name"]),
        reward_rules=rules,
        base_rate=float(raw["base_rate"]),
        point_value=float(raw["point_value"]),
    )


def load_cards(path: Path | str | None = None) -> list[CreditCard]:
    p = Path(path) if path else DEFAULT_CARDS_PATH
    if not p.exists():
        raise FileNotFoundError(f"cards file not found: {p}")
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    validated = validate_cards_file_payload(data)
    return [card_from_dict(c) for c in validated]


def load_cards_raw(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Return validated card dicts without building CreditCard objects."""
    p = Path(path) if path else DEFAULT_CARDS_PATH
    if not p.exists():
        raise FileNotFoundError(f"cards file not found: {p}")
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    return validate_cards_file_payload(data)


def save_cards(cards: list[dict[str, Any]], path: Path | str | None = None) -> None:
    p = Path(path) if path else DEFAULT_CARDS_PATH
    validate_cards_file_payload(cards)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(cards, f, indent=2)
        f.write("\n")


def upsert_card(card: dict[str, Any], path: Path | str | None = None) -> None:
    """Merge one validated card into the JSON file by name."""
    validate_card(card)
    p = Path(path) if path else DEFAULT_CARDS_PATH
    existing: list[dict[str, Any]] = []
    if p.exists():
        with p.open(encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list):
            existing = raw
    by_name: dict[str, dict[str, Any]] = {}
    for c in existing:
        if isinstance(c, dict) and c.get("name"):
            by_name[str(c["name"])] = c
    by_name[str(card["name"])] = card
    ordered = sorted(by_name.values(), key=lambda x: str(x["name"]).lower())
    save_cards(ordered, p)
