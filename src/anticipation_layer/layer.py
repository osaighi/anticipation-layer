"""
AnticipationLayer — Main entry point.

Ties together storage, update engine, and context assembly
into a single high-level interface.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Callable

from .models import Anticipation, Horizon, Category, Impact
from .storage import Storage
from .update_engine import UpdateEngine
from .context_assembly import ContextAssembly

logger = logging.getLogger(__name__)


class AnticipationLayer:
    """
    Persistent Temporal Awareness for AI Agents.

    Usage:
        layer = AnticipationLayer("./anticipations")

        # At each request, get anticipation context
        context = layer.get_context("Should we deploy on Thursday?")

        # When something happens, register the event
        layer.register_event("Hotfix #342 was merged")

        # During idle time, consolidate
        await layer.consolidate(current_context="...")
    """

    def __init__(
        self,
        storage_dir: str = "./anticipations",
        similarity_fn: Optional[Callable] = None,
        generate_fn: Optional[Callable] = None,
        top_k: int = 10,
        max_context_tokens: int = 500,
        config_path: Optional[str] = None,
    ):
        cfg = self._load_config(config_path)
        ue_cfg = cfg.get("update_engine", {})
        ci_cfg = cfg.get("context_injection", {})

        self.storage = Storage(storage_dir)
        self.engine = UpdateEngine(
            storage=self.storage,
            generate_fn=generate_fn,
            similarity_fn=similarity_fn,
            invalidation_threshold=ue_cfg.get("invalidation_threshold", 0.5),
            cascade_thresholds={
                Horizon.SHORT_TERM: ue_cfg.get("cascade_threshold_short", 0.3),
                Horizon.MEDIUM_TERM: ue_cfg.get("cascade_threshold_medium", 0.5),
            } if ue_cfg else None,
            weight_floor=ue_cfg.get("weight_floor", 0.3),
        )
        self.context_assembly = ContextAssembly(
            storage=self.storage,
            similarity_fn=similarity_fn,
            top_k=ci_cfg.get("top_k", top_k),
            min_relevance=ci_cfg.get("min_relevance", 0.1),
            max_tokens=ci_cfg.get("max_tokens", max_context_tokens),
        )

    @staticmethod
    def _load_config(config_path: Optional[str]) -> dict:
        """Load YAML config file if provided. Returns empty dict otherwise."""
        if config_path is None:
            return {}
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML is required to load a config file. "
                "Install it with: pip install pyyaml"
            )
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}

    # ─── Core Interface ───────────────────────────────────────────────

    def get_context(self, query: str) -> str:
        """
        Get formatted anticipation context for injection into an agent request.

        This is the main method called at every interaction. It's designed
        to be cheap: it reads pre-computed anticipations and filters by relevance.

        Args:
            query: The current user request or agent task.

        Returns:
            Formatted markdown block of relevant anticipations.
        """
        # Check for expired anticipations while we're at it
        self.engine.check_decay()
        return self.context_assembly.format_context(query)

    def add(
        self,
        prediction: str,
        horizon: Horizon,
        category: Category = Category.NEUTRAL,
        impact: Impact = Impact.MEDIUM,
        confidence: float = 0.5,
        domain: str = "general",
        suggested_actions: Optional[list[str]] = None,
    ) -> Anticipation:
        """
        Manually add an anticipation.

        Args:
            prediction: What the agent predicts will happen.
            horizon: Time horizon (short/medium/long term).
            category: Risk, opportunity, or neutral.
            impact: Expected impact level.
            confidence: How confident the agent is (0.0-1.0).
            domain: Domain or project this relates to.
            suggested_actions: Recommended actions based on this prediction.

        Returns:
            The created Anticipation object.
        """
        ant = Anticipation(
            prediction=prediction,
            horizon=horizon,
            category=category,
            impact=impact,
            confidence=confidence,
            domain=domain,
            suggested_actions=suggested_actions or [],
        )
        self.storage.add(ant)
        logger.info(f"Added anticipation: {ant.id} ({horizon.value})")
        return ant

    def register_event(self, event: str, invalidation_threshold: float = 0.5) -> list[Anticipation]:
        """
        Register an observed event.

        The event is compared against active anticipations. Those that are
        contradicted by the event are invalidated (prediction error signal).

        Args:
            event: Description of what happened.
            invalidation_threshold: Similarity threshold for invalidation.

        Returns:
            List of invalidated anticipations.
        """
        return self.engine.check_invalidation(event, threshold=invalidation_threshold)

    def mark_realized(self, anticipation_id: str) -> Optional[Anticipation]:
        """
        Mark an anticipation as realized (it came true).

        This feeds the learning loop — realized anticipations are archived
        with their confidence scores for calibration analysis.
        """
        return self.engine.register_realization(anticipation_id)

    async def consolidate(self, current_context: str = "") -> dict:
        """
        Run idle consolidation (the agent's "sleep cycle").

        Call this when the agent has no active requests. It reviews
        invalidations, reinforces good predictions, archives old ones,
        and optionally generates new anticipations.

        Args:
            current_context: Current state for generating new anticipations.

        Returns:
            Summary of consolidation actions.
        """
        return await self.engine.consolidate(current_context)

    # ─── Status & Diagnostics ─────────────────────────────────────────

    def status(self) -> str:
        """Get a formatted overview of all active anticipations."""
        return self.context_assembly.get_all_formatted()

    def metrics(self) -> dict:
        """
        Get performance metrics for the learning loop.

        Returns:
            Dict with realization_rate, calibration, surprise_rate, etc.
        """
        meta = self.storage.get_meta()
        total = meta.get("total_generated", 0)
        realized = meta.get("total_realized", 0)
        invalidated = meta.get("total_invalidated", 0)
        expired = meta.get("total_expired", 0)

        return {
            "total_generated": total,
            "total_realized": realized,
            "total_invalidated": invalidated,
            "total_expired": expired,
            "realization_rate": realized / total if total > 0 else 0,
            "invalidation_rate": invalidated / total if total > 0 else 0,
            "last_consolidation": meta.get("last_consolidation"),
        }
