"""
Context Assembly — Selects and formats anticipations for injection into agent context.

The key insight: instead of reasoning about the future at every request (expensive),
we pre-compute anticipations and inject them as passive context (cheap).
This turns a costly reasoning step into a simple context read.
"""

from __future__ import annotations

import logging
from typing import Optional, Callable

from .models import Anticipation, Horizon, Status
from .storage import Storage

logger = logging.getLogger(__name__)


class ContextAssembly:
    """
    Selects relevant anticipations and formats them for injection
    into the agent's context window.
    """

    def __init__(
        self,
        storage: Storage,
        similarity_fn: Optional[Callable] = None,
        top_k: int = 10,
        min_relevance: float = 0.1,
        max_tokens: int = 500,
    ):
        """
        Args:
            storage: Storage backend.
            similarity_fn: Semantic similarity function (a, b) -> float.
            top_k: Maximum number of anticipations to inject.
            min_relevance: Minimum relevance score to include.
            max_tokens: Approximate token budget for the anticipation context block.
        """
        self.storage = storage
        self.similarity_fn = similarity_fn or self._keyword_similarity
        self.top_k = top_k
        self.min_relevance = min_relevance
        self.max_tokens = max_tokens

    @staticmethod
    def _keyword_similarity(a: str, b: str) -> float:
        """Simple keyword overlap as fallback."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)

    def select(self, query: str) -> list[tuple[Anticipation, float]]:
        """
        Select the most relevant anticipations for a given query.

        Selection algorithm:
            1. Compute relevance = similarity(query, prediction)
            2. Score = relevance × weight (confidence × decay × impact)
            3. Filter by min_relevance
            4. Return top-K by score

        Args:
            query: The current user request or agent task.

        Returns:
            List of (anticipation, score) tuples, sorted by score descending.
        """
        active = self.storage.load_all_active()
        scored = []

        for ant in active:
            relevance = self.similarity_fn(query, ant.prediction)
            if relevance < self.min_relevance:
                # Even low-relevance high-impact items get a chance
                if ant.impact.value not in ("high", "critical"):
                    continue

            score = relevance * ant.weight
            # Boost high-impact items even with low direct relevance
            if ant.impact.value in ("high", "critical") and relevance > 0:
                score *= 1.5

            scored.append((ant, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:self.top_k]

    def format_context(self, query: str) -> str:
        """
        Generate the formatted anticipation context block for injection.

        Args:
            query: The current user request or agent task.

        Returns:
            Formatted markdown string ready for context injection.
        """
        selected = self.select(query)

        if not selected:
            return ""

        # Group by horizon
        by_horizon: dict[Horizon, list[tuple[Anticipation, float]]] = {}
        for ant, score in selected:
            by_horizon.setdefault(ant.horizon, []).append((ant, score))

        horizon_labels = {
            Horizon.SHORT_TERM: "Short term (next few days)",
            Horizon.MEDIUM_TERM: "Medium term (coming weeks/months)",
            Horizon.LONG_TERM: "Long term (coming months/year)",
        }

        lines = ["## Active Anticipations (temporal context)\n"]

        for horizon in Horizon:
            items = by_horizon.get(horizon)
            if not items:
                continue

            lines.append(f"### {horizon_labels[horizon]}")
            for ant, score in items:
                lines.append(ant.to_context_string())
            lines.append("")

        context = "\n".join(lines)

        # Rough token estimate (1 token ≈ 4 chars)
        estimated_tokens = len(context) / 4
        if estimated_tokens > self.max_tokens:
            logger.warning(
                f"Anticipation context ({estimated_tokens:.0f} est. tokens) "
                f"exceeds budget ({self.max_tokens}). Truncating."
            )
            # Re-select with fewer items
            self.top_k = max(3, self.top_k - 2)
            return self.format_context(query)

        return context

    def get_all_formatted(self) -> str:
        """
        Get all active anticipations formatted by horizon, without relevance filtering.
        Useful for status overview or consolidation review.
        """
        lines = ["## All Active Anticipations\n"]

        horizon_labels = {
            Horizon.SHORT_TERM: "Short term (1-7 days)",
            Horizon.MEDIUM_TERM: "Medium term (1-3 months)",
            Horizon.LONG_TERM: "Long term (6-12 months)",
        }

        for horizon in Horizon:
            anticipations = self.storage.load_horizon(horizon)
            active = [a for a in anticipations if a.status == Status.ACTIVE]
            lines.append(f"### {horizon_labels[horizon]} ({len(active)} active)")
            if active:
                active.sort(key=lambda a: a.weight, reverse=True)
                for ant in active:
                    lines.append(f"{ant.to_context_string()} [w={ant.weight:.2f}]")
            else:
                lines.append("- (none)")
            lines.append("")

        return "\n".join(lines)
