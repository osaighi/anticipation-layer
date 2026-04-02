"""
Base class for anticipation generators.

A generator takes the agent's current context and produces
structured anticipations for a given time horizon.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

from ..models import Anticipation, Horizon, Category, Impact

logger = logging.getLogger(__name__)

# System prompt template for anticipation generation
GENERATION_SYSTEM_PROMPT = """You are an Anticipation Engine — a specialized reasoning module 
that thinks about the future on behalf of an AI agent.

Your role is to analyze the current context and generate predictions about what 
might happen in the future. You think like a seasoned strategist: identifying risks 
before they materialize, spotting opportunities before they pass, and flagging 
neutral developments that could become relevant.

You generate anticipations for a specific time horizon:
- SHORT_TERM: 1-7 days ahead — tactical, immediate concerns
- MEDIUM_TERM: 1-3 months ahead — strategic, project-level developments  
- LONG_TERM: 6-12 months ahead — vision, trends, structural changes

For each anticipation, you must provide:
- prediction: A clear, specific statement about what might happen
- category: "risk", "opportunity", or "neutral"
- impact: "low", "medium", "high", or "critical"
- confidence: A float between 0.0 and 1.0 reflecting your certainty
- domain: The area this relates to (e.g., "engineering", "finance", "team")
- suggested_actions: 1-3 concrete actions the agent could take

IMPORTANT GUIDELINES:
- Be specific, not vague. "The project might have issues" is useless. 
  "The API migration may break 3 downstream services if not tested by Friday" is useful.
- Calibrate your confidence honestly. Don't default to 0.5 — think about it.
- Consider second-order effects. What happens if X happens? What does that cause?
- Balance risks and opportunities. Don't be only pessimistic or optimistic.
- Each anticipation should be actionable — if the agent can't do anything about it, 
  it's not worth anticipating.

Respond ONLY with a JSON array of anticipation objects. No preamble, no explanation."""

GENERATION_USER_PROMPT = """Current context:
{context}

Previously active anticipations (for continuity — avoid duplicates):
{existing_anticipations}

Generate exactly {count} anticipations for the {horizon} horizon.
Remember: be specific, calibrate confidence honestly, and make each one actionable.

Respond with a JSON array only."""


class BaseGenerator(ABC):
    """Abstract base class for anticipation generators."""

    def __init__(self, model: str, temperature: float = 0.7):
        self.model = model
        self.temperature = temperature

    @abstractmethod
    async def _call_llm(self, system: str, user: str) -> str:
        """Call the underlying LLM. Returns raw text response."""
        ...

    async def generate(
        self,
        context: str,
        horizon: Horizon,
        count: int = 3,
        existing: Optional[list[Anticipation]] = None,
    ) -> list[Anticipation]:
        """
        Generate anticipations for a given horizon from current context.

        Args:
            context: Current state description (project status, recent events, etc.)
            horizon: Which time horizon to generate for.
            count: Number of anticipations to generate.
            existing: Currently active anticipations (to avoid duplicates).

        Returns:
            List of new Anticipation objects.
        """
        existing_text = "None"
        if existing:
            existing_text = "\n".join(
                f"- [{a.horizon.value}] {a.prediction} (confidence: {a.confidence})"
                for a in existing
            )

        user_prompt = GENERATION_USER_PROMPT.format(
            context=context,
            existing_anticipations=existing_text,
            count=count,
            horizon=horizon.value,
        )

        try:
            raw = await self._call_llm(GENERATION_SYSTEM_PROMPT, user_prompt)
            return self._parse_response(raw, horizon)
        except Exception as e:
            logger.error(f"Generation failed for {horizon.value}: {e}")
            return []

    def _parse_response(self, raw: str, horizon: Horizon) -> list[Anticipation]:
        """Parse LLM JSON response into Anticipation objects."""
        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        try:
            entries = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}\nRaw: {raw[:200]}")
            return []

        if not isinstance(entries, list):
            entries = [entries]

        anticipations = []
        for entry in entries:
            try:
                ant = Anticipation(
                    prediction=entry["prediction"],
                    horizon=horizon,
                    category=Category(entry.get("category", "neutral")),
                    impact=Impact(entry.get("impact", "medium")),
                    confidence=float(entry.get("confidence", 0.5)),
                    domain=entry.get("domain", "general"),
                    suggested_actions=entry.get("suggested_actions", []),
                )
                anticipations.append(ant)
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed anticipation entry: {e}")
                continue

        return anticipations


# ─── Invalidation Checker ─────────────────────────────────────────

INVALIDATION_SYSTEM_PROMPT = """You are a Prediction Error Detector — a module that compares 
observed events against existing predictions to determine if any predictions have been 
contradicted or confirmed by reality.

Given an event and a list of active predictions, determine which predictions are:
- INVALIDATED: The event contradicts or makes the prediction no longer relevant
- CONFIRMED: The event supports or partially confirms the prediction
- UNAFFECTED: The event has no bearing on this prediction

Respond ONLY with a JSON array where each entry has:
- id: The anticipation ID
- status: "invalidated", "confirmed", or "unaffected"
- reason: Brief explanation (1 sentence)"""

INVALIDATION_USER_PROMPT = """Observed event:
{event}

Active predictions:
{predictions}

Analyze each prediction against this event. Respond with JSON array only."""


class LLMInvalidationChecker:
    """Uses an LLM to intelligently check if events invalidate predictions."""

    def __init__(self, generator: BaseGenerator):
        self.generator = generator

    async def check(
        self, event: str, anticipations: list[Anticipation]
    ) -> dict[str, str]:
        """
        Check which anticipations are affected by an event.

        Returns:
            Dict mapping anticipation ID to status ("invalidated", "confirmed", "unaffected")
        """
        predictions_text = "\n".join(
            f"- ID={a.id}: {a.prediction} (confidence: {a.confidence})"
            for a in anticipations
        )

        user_prompt = INVALIDATION_USER_PROMPT.format(
            event=event,
            predictions=predictions_text,
        )

        try:
            raw = await self.generator._call_llm(
                INVALIDATION_SYSTEM_PROMPT, user_prompt
            )
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            entries = json.loads(cleaned)
            return {
                entry["id"]: entry["status"]
                for entry in entries
                if "id" in entry and "status" in entry
            }
        except Exception as e:
            logger.error(f"LLM invalidation check failed: {e}")
            return {}
