"""
Anticipation Layer — Persistent Temporal Awareness for AI Agents

An architectural component that maintains a structured representation
of possible futures across multiple time horizons, injected as passive
context into every agent interaction.
"""

from .models import Anticipation, Horizon, Category, Impact, Status
from .layer import AnticipationLayer
from .update_engine import UpdateEngine
from .context_assembly import ContextAssembly
from .similarity import keyword_similarity, tfidf_similarity

__version__ = "0.1.0"
__all__ = [
    "Anticipation",
    "Horizon",
    "Category",
    "Impact",
    "Status",
    "AnticipationLayer",
    "UpdateEngine",
    "ContextAssembly",
    "keyword_similarity",
    "tfidf_similarity",
]
