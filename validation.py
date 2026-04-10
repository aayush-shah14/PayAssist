"""Validate card JSON (including LLM output) before persistence or loading."""

from __future__ import annotations

from datetime import date
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


def _normalize_cat(category: str) -> str:
    return category.strip().lower()


def _validate_period_value(period: Any, prefix: str) -> None:
    if period is None:
        return
    if isinstance(period, dict):
        start = period.get("start")
        end = period.get("end")
        if not _is_str(start) or not _is_str(end):
            raise ValidationError(
                f"{prefix}.period object requires string start and end (ISO dates)"
            )
        try:
            date.fromisoformat(start.strip()[:10])
            date.fromisoformat(end.strip()[:10])
        except ValueError as e:
            raise ValidationError(f"{prefix}.period start/end must be valid ISO dates") from e
        return
    if not _is_str(period):
        raise ValidationError(
            f"{prefix}.period must be null, a string label, or an object with start/end"
        )


def validate_rule(rule: Any, idx: int) -> None:
    prefix = f"rules[{idx}]"
    if not isinstance(rule, dict):
        raise ValidationError(f"{prefix} must be an object")

    rtype = rule.get("type")
    if rtype not in ALLOWED_RULE_TYPES:
        raise ValidationError(
            f"{prefix}.type must be one of {sorted(ALLOWED_RULE_TYPES)}"
        )

    if "category" not in rule:
        raise ValidationError(f"{prefix} missing required field 'category'")
    cat = rule["category"]
    if rtype == "universal_bonus":
        if not _is_str(cat):
            raise ValidationError(f"{prefix}.category must be a string (use 'other' for flat earn)")
        if _normalize_cat(cat) not in ALLOWED_CATEGORIES:
            raise ValidationError(
                f"{prefix}.category must be one of {sorted(ALLOWED_CATEGORIES)}"
            )
    else:
        if not _is_str(cat):
            raise ValidationError(f"{prefix}.category must be a string")
        if _normalize_cat(cat) not in ALLOWED_CATEGORIES:
            raise ValidationError(
                f"{prefix}.category must be one of {sorted(ALLOWED_CATEGORIES)}"
            )

    if "multiplier" not in rule:
        raise ValidationError(f"{prefix} missing required field 'multiplier'")
    mult = rule["multiplier"]
    if not _is_real_number(mult) or float(mult) <= 0:
        raise ValidationError(f"{prefix}.multiplier must be a number > 0")

    if "cap" in rule and rule["cap"] is not None:
        cap = rule["cap"]
        if not _is_real_number(cap) or float(cap) < 0:
            raise ValidationError(f"{prefix}.cap must be null or a number >= 0")

    if "cap_period" in rule and rule["cap_period"] is not None:
        if not _is_str(rule["cap_period"]):
            raise ValidationError(f"{prefix}.cap_period must be null or a string")

    if "period" in rule:
        _validate_period_value(rule["period"], prefix)

    if "priority" in rule and rule["priority"] is not None:
        pr = rule["priority"]
        if isinstance(pr, bool) or not _is_real_number(pr):
            raise ValidationError(f"{prefix}.priority must be an integer if present")
        if float(pr) != int(pr):
            raise ValidationError(f"{prefix}.priority must be a whole number")
        if int(pr) < 0:
            raise ValidationError(f"{prefix}.priority must be non-negative")

    if "conditions" in rule and rule["conditions"] is not None:
        if not isinstance(rule["conditions"], dict):
            raise ValidationError(f"{prefix}.conditions must be an object or null")

    if "exclusions" in rule and rule["exclusions"] is not None:
        ex = rule["exclusions"]
        if not isinstance(ex, list):
            raise ValidationError(f"{prefix}.exclusions must be an array or null")
        for j, item in enumerate(ex):
            if not _is_str(item):
                raise ValidationError(f"{prefix}.exclusions[{j}] must be a string")


def validate_card(card: Any) -> dict[str, Any]:
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
