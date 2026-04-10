"""LLM-based extraction of structured card rewards from raw website text (parsing only)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from validation import ValidationError, validate_card


def _norm_rule_cat_key(rule: dict[str, Any]) -> str:
    c = rule.get("category")
    if c is None:
        return ""
    return str(c).strip().lower()


def _norm_rule_type_key(rule: dict[str, Any]) -> str:
    return str(rule.get("type", "")).strip()


def _norm_rule_conditions_nonempty(rule: dict[str, Any]) -> bool:
    c = rule.get("conditions")
    return isinstance(c, dict) and len(c) > 0


def _normalize_parsed_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge unconditional duplicates per (category, type): keep highest multiplier.

    Rules with non-empty conditions are kept separate; missing priority gets a bump
    so they win over broad rules when the engine sorts by (priority, multiplier).
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rules:
        if not isinstance(r, dict):
            continue
        key = (_norm_rule_cat_key(r), _norm_rule_type_key(r))
        groups.setdefault(key, []).append(r)

    out: list[dict[str, Any]] = []
    for (_, _), bucket in groups.items():
        conditional = [dict(x) for x in bucket if _norm_rule_conditions_nonempty(x)]
        unconditional = [x for x in bucket if not _norm_rule_conditions_nonempty(x)]

        for r in conditional:
            if r.get("priority") is None:
                r["priority"] = 10
            out.append(r)

        if unconditional:
            best = max(unconditional, key=lambda x: float(x.get("multiplier", 0)))
            merged = dict(best)
            if merged.get("priority") is None:
                merged["priority"] = 0
            out.append(merged)

    return out


def _normalize_parsed_card(card: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of card with normalized rules list."""
    rules = card.get("rules")
    if not isinstance(rules, list):
        return card
    normalized = _normalize_parsed_rules([x for x in rules if isinstance(x, dict)])
    return {**card, "rules": normalized}

SYSTEM_PROMPT = (
    "You extract ONGOING SPEND REWARD RULES from credit card marketing or terms text. "
    "Respond with JSON only. No markdown fences or commentary. "
    "Ignore signup bonuses, statement credits, free trials, companion passes, "
    "one-time offers, and any benefit that is not routine earn on purchase volume. "
    "Focus only on recurring earn rates (e.g. 3x on dining, 5% at grocery stores). "
    "Infer higher priority for narrower rules (e.g. portal-specific > generic travel). "
    "Categories must be from the allowed list only."
)

USER_INSTRUCTIONS = """
Extract structured credit card rewards from the text below.

Return ONE JSON object with exactly these top-level keys:
- "name" (string, official product name)
- "point_value" (number > 0, estimated cash value per point earned, e.g. 0.02)
- "base_rate" (number >= 0, default earn multiplier when no rule applies)
- "rules" (array of rule objects)

Each rule object MUST include these REQUIRED keys:
- "type": one of "category_bonus", "rotating_category", "relationship_bonus", "universal_bonus"
- "category": one of dining, grocery, travel, gas, rent, online, other
  (for "universal_bonus" use "other" as the stored category; the engine still applies it to all spend)
- "multiplier": number > 0

OPTIONAL keys (include when applicable, otherwise omit or use null):
- "conditions": object mapping field names to values for matching transactions.
  Use keys like "booking_channel", "channel" (e.g. "online"), or other clear keys.
  Example: {{"booking_channel": "chase_travel", "channel": "online"}}
- "exclusions": array of lowercase tokens (merchant substrings or category names to block).
  Example: ["walmart", "target"] for grocery rules that exclude big-box.
- "cap": number >= 0 or null (max eligible spend for this rule in the cap_period, if stated)
- "cap_period": string or null, e.g. "monthly", "quarterly", "annual"
- "period": either null, a short string label (e.g. "quarterly"), OR an object with ISO date strings:
  {{"start": "2026-01-01", "end": "2026-03-31"}} for calendar-bound promos
- "priority": integer; higher = wins when multiple rules match (default 0 if omitted).
  More specific rules (portal, merchant) should have higher priority than broad category rules.

Do NOT include: signup bonuses, credits (hotel/airline credits, DashPass, etc.),
lounge access unless tied to a spend multiplier, or one-time offers.

Allowed categories (output lowercase):
dining, grocery, travel, gas, rent, online, other

---
SOURCE TEXT:
---
{body}
---
"""


def parse_card_benefits(file_path: str, *, model: str | None = None) -> dict:
    """
    Read a .txt file, call the OpenAI API (temperature=0, JSON object response),
    validate, normalize rules, re-validate, return card dict.
    """
    path = Path(file_path)
    body = path.read_text(encoding="utf-8")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)
    model_name = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    user_content = USER_INSTRUCTIONS.format(body=body[:120_000])

    completion = client.chat.completions.create(
        model=model_name,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    raw = completion.choices[0].message.content
    if not raw:
        raise ValidationError("LLM returned empty content")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValidationError(f"LLM output is not valid JSON: {e}") from e

    validate_card(data)
    normalized = _normalize_parsed_card(data)
    return validate_card(normalized)


def sync_benefits_directory(
    directory: str,
    *,
    cards_path: str | None = None,
    model: str | None = None,
) -> None:
    """Parse every *.txt in ``directory`` and upsert into cards.json by card name."""
    from storage import DEFAULT_CARDS_PATH, upsert_card

    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(str(root))

    out_path = Path(cards_path) if cards_path else DEFAULT_CARDS_PATH
    for txt in sorted(root.glob("*.txt")):
        card = parse_card_benefits(str(txt), model=model)
        upsert_card(card, out_path)
        print(f"Upserted {card['name']!r} from {txt.name} -> {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse benefit .txt files into cards.json")
    parser.add_argument(
        "path",
        nargs="?",
        default="benefits_raw",
        help="Directory of .txt files (default: benefits_raw) or a single .txt file",
    )
    parser.add_argument(
        "--cards",
        dest="cards_path",
        default=None,
        help="Path to cards.json (default: packaged cards.json next to storage.py)",
    )
    parser.add_argument("--model", default=None, help="OpenAI model id")
    args = parser.parse_args()
    p = Path(args.path)
    if p.is_file() and p.suffix.lower() == ".txt":
        from storage import DEFAULT_CARDS_PATH, upsert_card

        card = parse_card_benefits(str(p), model=args.model)
        upsert_card(card, Path(args.cards_path) if args.cards_path else DEFAULT_CARDS_PATH)
        print(json.dumps(card, indent=2))
    elif p.is_dir():
        sync_benefits_directory(
            str(p), cards_path=args.cards_path, model=args.model
        )
    else:
        raise SystemExit(f"Not a .txt file or directory: {p}")


if __name__ == "__main__":
    main()
