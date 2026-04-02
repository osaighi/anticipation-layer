"""
LLM-powered anticipation generators.

These modules use language models to generate anticipations
from the agent's current context — the core "thinking about the future"
capability of the Anticipation Layer.
"""

from .claude import ClaudeGenerator
from .base import BaseGenerator

__all__ = ["ClaudeGenerator", "BaseGenerator"]
