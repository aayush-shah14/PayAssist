"""Validate card JSON (including LLM output) before persistence or loading."""

from __future__ import annotations

from typing import Any

ALLOWED_CATEGORIES = frozenset(
    {"dining", "grocery", "travel", "gas", "rent", "online", "other"}
)
ALLOWED_RULE_TYPES = frozenset(
    {"category_bonus", "rotating_category", "relationship_bonus", "universal_bonus"}
)


class ValidationError(ValueError):
    """Raised when a card record fails schema checks."""


def _is_str(x: Any) -> bool:
    return isinstance(x, str)


def _is_real_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_rule(rule: Any, idx: int) -> None:
    prefix = f"rules[{idx}]"
    if not isinstance(rule, dict):
        raise ValidationError(f"{prefix} must be an object")

    rtype = rule.get("type")
    if rtype not in ALLOWED_RULE_TYPES:
        raise ValidationError(
            f"{prefix}.type must be one of {sorted(ALLOWED_RULE_TYPES)}"
        )

    if "multiplier" not in rule:
        raise ValidationError(f"{prefix} missing multiplier")
    mult = rule["multiplier"]
    if not _is_real_number(mult) or float(mult) <= 0:
        raise ValidationError(f"{prefix}.multiplier must be a number > 0")

    if "cap" not in rule:
        raise ValidationError(f"{prefix} missing cap (use null if none)")
    if "period" not in rule:
        raise ValidationError(f"{prefix} missing period (use null if none)")

    if rtype != "universal_bonus":
        cat = rule.get("category")
        if not _is_str(cat):
            raise ValidationError(f"{prefix}.category must be a string")
        if _normalize_cat(cat) not in ALLOWED_CATEGORIES:
            raise ValidationError(
                f"{prefix}.category must be one of {sorted(ALLOWED_CATEGORIES)}"
            )
    else:
        cat = rule.get("category")
        if cat is not None:
            if not _is_str(cat):
                raise ValidationError(f"{prefix}.category must be string or null")
            if _normalize_cat(cat) not in ALLOWED_CATEGORIES:
                raise ValidationError(f"{prefix}.category invalid for universal_bonus")

    cap = rule["cap"]
    if cap is not None and (not _is_real_number(cap) or float(cap) < 0):
        raise ValidationError(f"{prefix}.cap must be null or a number >= 0")

    period = rule["period"]
    if period is not None and not _is_str(period):
        raise ValidationError(f"{prefix}.period must be null or a string")

    if "conditions" in rule and rule["conditions"] is not None:
        if not isinstance(rule["conditions"], dict):
            raise ValidationError(f"{prefix}.conditions must be an object or null")


def _normalize_cat(category: str) -> str:
    return category.strip().lower()


def validate_card(card: Any) -> dict[str, Any]:
    """
    Validate a single card dict. Returns a normalized copy-safe dict (same structure).

    Raises ValidationError on failure.
    """
    if not isinstance(card, dict):
        raise ValidationError("card must be an object")

    required_top = ("name", "point_value", "base_rate", "rules")
    for key in required_top:
        if key not in card:
            raise ValidationError(f"card missing required field {key!r}")

    name = card["name"]
    if not _is_str(name) or not name.strip():
        raise ValidationError("card.name must be a non-empty string")

    pv = card["point_value"]
    if not _is_real_number(pv) or float(pv) <= 0:
        raise ValidationError("card.point_value must be a number > 0")

    br = card["base_rate"]
    if not _is_real_number(br) or float(br) < 0:
        raise ValidationError("card.base_rate must be a number >= 0")

    rules = card["rules"]
    if not isinstance(rules, list):
        raise ValidationError("card.rules must be an array")

    for i, rule in enumerate(rules):
        validate_rule(rule, i)

    return card


def validate_cards_file_payload(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise ValidationError("root JSON must be an array of cards")
    out: list[dict[str, Any]] = []
    for i, card in enumerate(data):
        try:
            out.append(validate_card(card))
        except ValidationError as e:
            raise ValidationError(f"cards[{i}]: {e}") from e
    return out
