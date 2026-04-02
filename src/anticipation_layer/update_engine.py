"""
Update Engine — Four bio-inspired mechanisms for maintaining anticipations.

1. Invalidation (Prediction Error Signal)
2. Temporal Decay
3. Cascading Reappraisal
4. Idle Consolidation
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Callable

from .models import Anticipation, Horizon, Status
from .storage import Storage

logger = logging.getLogger(__name__)

# Cascade thresholds: what % of invalidation triggers reappraisal of the next horizon
CASCADE_THRESHOLDS = {
    Horizon.SHORT_TERM: 0.3,   # 30% invalidation → reappraise medium term
    Horizon.MEDIUM_TERM: 0.5,  # 50% invalidation → reappraise long term
}

WEIGHT_FLOOR = 0.3  # Below this weight, anticipation is flagged for refresh


class UpdateEngine:
    """
    Manages the four update mechanisms for the Anticipation Layer.

    The engine is designed to be cost-efficient: it does nothing when
    reality confirms predictions, and only triggers computation when
    something unexpected happens or time-based thresholds are crossed.
    """

    def __init__(
        self,
        storage: Storage,
        generate_fn: Optional[Callable] = None,
        similarity_fn: Optional[Callable] = None,
    ):
        """
        Args:
            storage: Storage backend for anticipations.
            generate_fn: Async function to generate new anticipations via LLM.
                         Signature: (context: str, horizon: Horizon, count: int) -> list[Anticipation]
            similarity_fn: Function to compute semantic similarity between two strings.
                           Signature: (a: str, b: str) -> float (0.0 to 1.0)
        """
        self.storage = storage
        self.generate_fn = generate_fn
        self.similarity_fn = similarity_fn or self._default_similarity

    @staticmethod
    def _default_similarity(a: str, b: str) -> float:
        """Simple keyword overlap similarity as fallback."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    # ─── Mechanism 1: Invalidation (Prediction Error Signal) ──────────

    def check_invalidation(self, event: str, threshold: float = 0.5) -> list[Anticipation]:
        """
        Compare an observed event against all active anticipations.
        If the event contradicts a prediction (high similarity but opposite outcome),
        invalidate it.

        This is the most cost-efficient mechanism: it's passive most of the time
        and only fires on "surprise" — when reality diverges from predictions.

        Args:
            event: Description of the observed event.
            threshold: Similarity threshold to consider an anticipation relevant.

        Returns:
            List of anticipations that were invalidated.
        """
        invalidated = []
        active = self.storage.load_all_active()

        for anticipation in active:
            similarity = self.similarity_fn(event, anticipation.prediction)
            if similarity >= threshold:
                logger.info(
                    f"Invalidating {anticipation.id}: event '{event[:50]}...' "
                    f"contradicts prediction (similarity={similarity:.2f})"
                )
                anticipation.invalidate(reason=event)
                self.storage.update(anticipation)
                self.storage.log_invalidation(anticipation, event)
                invalidated.append(anticipation)

        # Check if cascade should be triggered
        if invalidated:
            self._check_cascade(invalidated)

        return invalidated

    def register_realization(self, anticipation_id: str) -> Optional[Anticipation]:
        """
        Mark an anticipation as realized (it came true).
        Boosts confidence calibration for the learning loop.
        """
        for horizon in Horizon:
            anticipations = self.storage.load_horizon(horizon)
            for ant in anticipations:
                if ant.id == anticipation_id:
                    ant.realize()
                    self.storage.update(ant)
                    self.storage._increment_meta("total_realized")
                    logger.info(f"Realized: {ant.id}")
                    return ant
        return None

    # ─── Mechanism 2: Temporal Decay ──────────────────────────────────

    def check_decay(self) -> dict[str, list[Anticipation]]:
        """
        Check all active anticipations for temporal decay.

        Anticipations whose weight has dropped below the floor threshold
        are flagged for refresh. Expired anticipations are marked accordingly.

        Returns:
            Dict with 'expired' and 'needs_refresh' lists.
        """
        expired = []
        needs_refresh = []

        for horizon in Horizon:
            anticipations = self.storage.load_horizon(horizon)
            for ant in anticipations:
                if ant.status != Status.ACTIVE:
                    continue

                if ant.is_expired:
                    ant.expire()
                    self.storage.update(ant)
                    self.storage._increment_meta("total_expired")
                    expired.append(ant)
                    logger.info(f"Expired: {ant.id} (age={ant.age_hours:.1f}h)")

                elif ant.weight < WEIGHT_FLOOR:
                    needs_refresh.append(ant)
                    logger.info(
                        f"Needs refresh: {ant.id} (weight={ant.weight:.3f})"
                    )

        return {"expired": expired, "needs_refresh": needs_refresh}

    # ─── Mechanism 3: Cascading Reappraisal ───────────────────────────

    def _check_cascade(self, invalidated: list[Anticipation]) -> None:
        """
        Check if invalidations should trigger a cascading reappraisal.

        If >30% of short-term anticipations are invalidated, trigger
        medium-term reappraisal. If >50% of medium-term are invalidated,
        trigger long-term reappraisal.
        """
        # Count invalidations per horizon
        for horizon in [Horizon.SHORT_TERM, Horizon.MEDIUM_TERM]:
            all_in_horizon = self.storage.load_horizon(horizon)
            if not all_in_horizon:
                continue

            invalidated_in_horizon = [
                a for a in invalidated if a.horizon == horizon
            ]
            invalidation_rate = len(invalidated_in_horizon) / len(all_in_horizon)

            threshold = CASCADE_THRESHOLDS.get(horizon)
            if threshold and invalidation_rate >= threshold:
                next_horizon = (
                    Horizon.MEDIUM_TERM if horizon == Horizon.SHORT_TERM
                    else Horizon.LONG_TERM
                )
                logger.warning(
                    f"CASCADE: {invalidation_rate:.0%} of {horizon.value} invalidated "
                    f"(threshold={threshold:.0%}). Triggering {next_horizon.value} reappraisal."
                )
                self._reappraise_horizon(next_horizon)

    def _reappraise_horizon(self, horizon: Horizon) -> None:
        """
        Reappraise all anticipations in a horizon.
        Marks them all for refresh, effectively forcing regeneration.
        """
        anticipations = self.storage.load_horizon(horizon)
        for ant in anticipations:
            if ant.status == Status.ACTIVE:
                ant.expire()  # Force regeneration
                self.storage.update(ant)
                logger.info(f"Cascade-expired: {ant.id} in {horizon.value}")

    # ─── Mechanism 4: Idle Consolidation ──────────────────────────────

    async def consolidate(self, current_context: str = "") -> dict:
        """
        Run idle consolidation — the agent's "sleep cycle".

        This is triggered when the agent has no active requests.
        It reviews recent invalidations, detects patterns, reinforces
        good predictions, and proactively generates new anticipations.

        Args:
            current_context: Current state/context for generating new anticipations.

        Returns:
            Summary of consolidation actions taken.
        """
        summary = {
            "reviewed_invalidations": 0,
            "reinforced": 0,
            "archived": 0,
            "generated": 0,
        }

        # 1. Review and archive non-active anticipations
        for horizon in Horizon:
            all_ants = self.storage.load_horizon(horizon)
            non_active = [a for a in all_ants if a.status != Status.ACTIVE]
            if non_active:
                self.storage.archive_horizon(horizon)
                summary["archived"] += len(non_active)

        # 2. Check temporal decay
        decay_result = self.check_decay()
        summary["reviewed_invalidations"] = len(decay_result["expired"])

        # 3. Reinforce surviving anticipations
        active = self.storage.load_all_active()
        for ant in active:
            if ant.age_hours > 24 and ant.status == Status.ACTIVE:
                # Surviving anticipations get a small confidence boost
                boost = min(0.05, 1.0 - ant.confidence)
                ant.confidence = min(1.0, ant.confidence + boost)
                self.storage.update(ant)
                summary["reinforced"] += 1

        # 4. Generate new anticipations if generator is available
        if self.generate_fn and current_context:
            for horizon in Horizon:
                existing = self.storage.load_horizon(horizon)
                active_count = sum(1 for a in existing if a.status == Status.ACTIVE)
                if active_count < 3:  # Maintain minimum anticipation count
                    try:
                        new_ants = await self.generate_fn(
                            current_context, horizon, count=3 - active_count
                        )
                        for ant in new_ants:
                            self.storage.add(ant)
                            summary["generated"] += 1
                    except Exception as e:
                        logger.error(f"Failed to generate anticipations for {horizon.value}: {e}")

        # 5. Update metadata
        self.storage.update_meta({
            "last_consolidation": datetime.utcnow().isoformat(),
        })

        logger.info(f"Consolidation complete: {summary}")
        return summary
