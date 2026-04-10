"""Domain models for transactions, user spend tracking, and reward rule shapes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, TypedDict, Union


class RulePeriodWindow(TypedDict, total=False):
    start: str
    end: str


class CategoryBonusRule(TypedDict, total=False):
    type: Literal["category_bonus"]
    category: str
    multiplier: float
    cap: float | None
    cap_period: str | None
    period: str | RulePeriodWindow | None
    conditions: dict[str, Any]
    exclusions: list[str]
    priority: int
    start_date: date
    end_date: date


class RotatingCategoryRule(TypedDict, total=False):
    type: Literal["rotating_category"]
    category: str
    multiplier: float
    cap: float | None
    cap_period: str | None
    period: str | RulePeriodWindow | None
    conditions: dict[str, Any]
    exclusions: list[str]
    priority: int
    start_date: date
    end_date: date


class RelationshipBonusRule(TypedDict, total=False):
    type: Literal["relationship_bonus"]
    category: str
    multiplier: float
    cap: float | None
    cap_period: str | None
    period: str | RulePeriodWindow | None
    conditions: dict[str, Any]
    exclusions: list[str]
    priority: int
    start_date: date
    end_date: date


class UniversalBonusRule(TypedDict, total=False):
    type: Literal["universal_bonus"]
    category: str
    multiplier: float
    cap: float | None
    cap_period: str | None
    period: str | RulePeriodWindow | None
    conditions: dict[str, Any]
    exclusions: list[str]
    priority: int
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
class UserProfile:
    """
    Optional spend tracking for cap_period limits.

    Keys in per_rule_spend: "{card_name}#{rule_index}" -> dollars already counted
    toward that rule's cap in the current cap_period (caller-defined window).
    """

    per_rule_spend: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Transaction:
    merchant: str
    category: str
    amount: float
    channel: str | None = None
    booking_channel: str | None = None
    timestamp: str | None = None
    txn_date: date | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class RewardComputation:
    value_dollars: float
    points: float
    explanation: str
