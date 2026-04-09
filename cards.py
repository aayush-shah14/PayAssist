"""Runtime credit card model (loaded from cards.json)."""

from __future__ import annotations

from dataclasses import dataclass, field

from models import RewardRule


@dataclass
class CreditCard:
    name: str
    reward_rules: list[RewardRule] = field(default_factory=list)
    base_rate: float = 1.0
    point_value: float = 0.01
