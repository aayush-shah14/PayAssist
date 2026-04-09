"""LLM-based extraction of structured card rewards from raw website text (parsing only)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from openai import OpenAI

from validation import ValidationError, validate_card

SYSTEM_PROMPT = (
    "You convert credit card marketing or terms text into a single JSON object. "
    "Respond with JSON only. Never include code fences or commentary. "
    "Use the exact key names requested by the user. "
    "All multipliers must be positive numbers. "
    "Categories must be chosen only from the allowed list."
)

USER_INSTRUCTIONS = """
Extract structured credit card rewards from the text below.

Return ONE JSON object with exactly these top-level keys:
- "name" (string, official product name)
- "point_value" (number, estimated cash value per point earned, e.g. 0.02 means 2 cents per point)
- "base_rate" (number, default earn multiplier when no rule applies, e.g. 1.0)
- "rules" (array of rule objects)

Each rule object MUST include ALL of these keys:
- "type": one of "category_bonus", "rotating_category", "relationship_bonus", "universal_bonus"
- "category": one of dining, grocery, travel, gas, rent, online, other — use null ONLY for universal_bonus
- "multiplier": number > 0 (points or percent expressed as multiplier per $1 of eligible spend)
- "cap": number >= 0 or null (maximum eligible spend this rule applies to per its period, if stated)
- "period": string such as "monthly", "quarterly", "annual", or null if not stated
- "conditions": JSON object (use empty object {{}} if none). For relationship bonuses, encode
  requirements as key/value pairs that could be matched against transaction metadata later.

Mapping guidance:
- Map merchant types to the closest allowed category; use "other" when unclear.
- Quarterly 5% categories → rotating_category, period "quarterly".
- Requires bank relationship → relationship_bonus with details in conditions.
- Flat cash back on everything → universal_bonus, category null.

Allowed categories (case-insensitive in source text; output lowercase):
dining, grocery, travel, gas, rent, online, other

---
SOURCE TEXT:
---
{body}
---
"""


def parse_card_benefits(file_path: str, *, model: str | None = None) -> dict:
    """
    Read a .txt file, call the OpenAI API (temperature=0, JSON object response), validate, return card dict.
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

    return validate_card(data)


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
