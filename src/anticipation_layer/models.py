"""
Core data models for the Anticipation Layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class Horizon(str, Enum):
    """Time horizons for anticipations."""
    SHORT_TERM = "short_term"      # 1-7 days
    MEDIUM_TERM = "medium_term"    # 1-3 months
    LONG_TERM = "long_term"        # 6-12 months


class Category(str, Enum):
    """Anticipation categories."""
    RISK = "risk"
    OPPORTUNITY = "opportunity"
    NEUTRAL = "neutral"


class Impact(str, Enum):
    """Impact levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Status(str, Enum):
    """Anticipation lifecycle status."""
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    REALIZED = "realized"
    ARCHIVED = "archived"


# Default decay rates (lambda) per horizon
DECAY_RATES = {
    Horizon.SHORT_TERM: 0.3,
    Horizon.MEDIUM_TERM: 0.05,
    Horizon.LONG_TERM: 0.01,
}

# Default TTL per horizon
DEFAULT_TTL = {
    Horizon.SHORT_TERM: timedelta(hours=48),
    Horizon.MEDIUM_TERM: timedelta(weeks=2),
    Horizon.LONG_TERM: timedelta(days=60),
}

# Impact weight multipliers
IMPACT_WEIGHTS = {
    Impact.LOW: 0.25,
    Impact.MEDIUM: 0.5,
    Impact.HIGH: 0.75,
    Impact.CRITICAL: 1.0,
}


@dataclass
class Anticipation:
    """
    A single anticipation entry.

    Represents a prediction about a future state, stored persistently
    and injected into the agent's context at each interaction.
    """

    prediction: str
    horizon: Horizon
    category: Category = Category.NEUTRAL
    impact: Impact = Impact.MEDIUM
    confidence: float = 0.5
    domain: str = "general"
    suggested_actions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

    # Auto-generated fields
    id: str = field(default_factory=lambda: f"ant-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}")
    created: datetime = field(default_factory=datetime.utcnow)
    expires: Optional[datetime] = None
    status: Status = Status.ACTIVE
    invalidated_by: Optional[str] = None
    realized: bool = False
    realization_date: Optional[datetime] = None
    refresh_count: int = 0

    def __post_init__(self):
        if self.expires is None:
            self.expires = self.created + DEFAULT_TTL[self.horizon]
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")

    @property
    def age_hours(self) -> float:
        """Age of the anticipation in hours."""
        return (datetime.utcnow() - self.created).total_seconds() / 3600

    @property
    def is_expired(self) -> bool:
        """Whether the anticipation has passed its TTL."""
        return datetime.utcnow() > self.expires

    @property
    def decay_lambda(self) -> float:
        """Decay rate for this anticipation's horizon."""
        return DECAY_RATES[self.horizon]

    @property
    def weight(self) -> float:
        """
        Current weight of the anticipation, incorporating temporal decay.

        weight(t) = confidence × e^(-λ × age_in_days) × impact_multiplier
        """
        import math
        age_days = self.age_hours / 24
        temporal_weight = math.exp(-self.decay_lambda * age_days)
        impact_mult = IMPACT_WEIGHTS[self.impact]
        return self.confidence * temporal_weight * impact_mult

    def invalidate(self, reason: str) -> None:
        """Mark this anticipation as invalidated by an observed event."""
        self.status = Status.INVALIDATED
        self.invalidated_by = reason

    def realize(self) -> None:
        """Mark this anticipation as realized (it came true)."""
        self.status = Status.REALIZED
        self.realized = True
        self.realization_date = datetime.utcnow()

    def expire(self) -> None:
        """Mark this anticipation as expired."""
        self.status = Status.EXPIRED

    def refresh(self, new_confidence: Optional[float] = None, new_expires: Optional[datetime] = None) -> None:
        """Refresh the anticipation, extending its TTL."""
        self.refresh_count += 1
        if new_confidence is not None:
            self.confidence = new_confidence
        self.expires = new_expires or (datetime.utcnow() + DEFAULT_TTL[self.horizon])

    def to_context_string(self) -> str:
        """Format for injection into agent context."""
        icon = "⚠️" if self.category == Category.RISK else "✅" if self.category == Category.OPPORTUNITY else "ℹ️"
        return f"- {icon} [{self.impact.value.upper()}] {self.prediction} (confidence: {self.confidence:.0%})"

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "created": self.created.isoformat(),
            "expires": self.expires.isoformat() if self.expires else None,
            "confidence": self.confidence,
            "category": self.category.value,
            "domain": self.domain,
            "horizon": self.horizon.value,
            "prediction": self.prediction,
            "impact": self.impact.value,
            "suggested_actions": self.suggested_actions,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "invalidated_by": self.invalidated_by,
            "realized": self.realized,
            "realization_date": self.realization_date.isoformat() if self.realization_date else None,
            "refresh_count": self.refresh_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Anticipation:
        """Deserialize from dictionary."""
        ant = cls(
            prediction=data["prediction"],
            horizon=Horizon(data["horizon"]),
            category=Category(data.get("category", "neutral")),
            impact=Impact(data.get("impact", "medium")),
            confidence=data.get("confidence", 0.5),
            domain=data.get("domain", "general"),
            suggested_actions=data.get("suggested_actions", []),
            dependencies=data.get("dependencies", []),
        )
        ant.id = data.get("id", ant.id)
        ant.created = datetime.fromisoformat(data["created"]) if "created" in data else ant.created
        ant.expires = datetime.fromisoformat(data["expires"]) if data.get("expires") else ant.expires
        ant.status = Status(data.get("status", "active"))
        ant.invalidated_by = data.get("invalidated_by")
        ant.realized = data.get("realized", False)
        ant.realization_date = (
            datetime.fromisoformat(data["realization_date"]) if data.get("realization_date") else None
        )
        ant.refresh_count = data.get("refresh_count", 0)
        return ant
