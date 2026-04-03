"""
Claude-powered anticipation generator.

Uses the Anthropic API to generate anticipations from context.
"""

from __future__ import annotations

import logging
from typing import Optional

from .base import BaseGenerator

logger = logging.getLogger(__name__)


class ClaudeGenerator(BaseGenerator):
    """
    Generate anticipations using Anthropic's Claude API.

    Usage:
        from anticipation_layer.generators import ClaudeGenerator

        generator = ClaudeGenerator(api_key="sk-ant-...")
        anticipations = await generator.generate(
            context="Sprint ends Friday. 2 items still in progress.",
            horizon=Horizon.SHORT_TERM,
            count=3,
        )
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ):
        """
        Args:
            api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.
            model: Claude model to use.
            temperature: Sampling temperature (higher = more creative anticipations).
            max_tokens: Max tokens for the response.
        """
        super().__init__(model=model, temperature=temperature)
        self.max_tokens = max_tokens

        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for ClaudeGenerator. "
                "Install it with: pip install anticipation-layer[llm]"
            )

        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def _call_llm(self, system: str, user: str) -> str:
        """Call Claude API and return text response."""
        import anthropic

        try:
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )

            # Extract text from response
            text_parts = [
                block.text
                for block in message.content
                if hasattr(block, "text")
            ]
            return "\n".join(text_parts)

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            raise


class ClaudeGeneratorSync:
    """
    Synchronous wrapper around ClaudeGenerator for non-async contexts.

    Usage:
        generator = ClaudeGeneratorSync(api_key="sk-ant-...")
        anticipations = generator.generate(context="...", horizon=Horizon.SHORT_TERM)
    """

    def __init__(self, **kwargs):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required. "
                "Install with: pip install anticipation-layer[llm]"
            )

        self._api_key = kwargs.get("api_key")
        self._model = kwargs.get("model", "claude-sonnet-4-20250514")
        self._temperature = kwargs.get("temperature", 0.7)
        self._max_tokens = kwargs.get("max_tokens", 2000)
        self.client = anthropic.Anthropic(api_key=self._api_key)

    def generate(self, context, horizon, count=3, existing=None):
        """Synchronous generation using the sync Anthropic client."""
        from .base import BaseGenerator, GENERATION_SYSTEM_PROMPT, GENERATION_USER_PROMPT

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

        message = self.client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=GENERATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = "\n".join(
            block.text for block in message.content if hasattr(block, "text")
        )

        return BaseGenerator._parse_response(raw, horizon)
