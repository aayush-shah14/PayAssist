"""Domain models for transactions and reward rule shapes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, TypedDict, Union


class CategoryBonusRule(TypedDict, total=False):
    type: Literal["category_bonus"]
    category: str
    multiplier: float
    cap: float | None
    period: str | None
    conditions: dict[str, Any]
    start_date: date
    end_date: date


class RotatingCategoryRule(TypedDict, total=False):
    type: Literal["rotating_category"]
    category: str
    multiplier: float
    cap: float | None
    period: str | None
    conditions: dict[str, Any]
    start_date: date
    end_date: date


class RelationshipBonusRule(TypedDict, total=False):
    type: Literal["relationship_bonus"]
    category: str
    multiplier: float
    cap: float | None
    period: str | None
    conditions: dict[str, Any]
    start_date: date
    end_date: date


class UniversalBonusRule(TypedDict, total=False):
    """Flat earn on all purchases (common for cash-back cards)."""

    type: Literal["universal_bonus"]
    multiplier: float
    cap: float | None
    period: str | None
    conditions: dict[str, Any]
    start_date: date
    end_date: date


RewardRule = Union[
    CategoryBonusRule,
    RotatingCategoryRule,
    RelationshipBonusRule,
    UniversalBonusRule,
    dict[str, Any],
]


@dataclass(frozen=True)
class Transaction:
    merchant: str
    category: str
    amount: float
    txn_date: date | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class RewardComputation:
    value_dollars: float
    points: float
    explanation: str
