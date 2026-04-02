"""
LangGraph integration for the Anticipation Layer.

Provides nodes and utilities to plug the Anticipation Layer
into a LangGraph agent graph.

Usage:
    from anticipation_layer.integrations.langgraph import (
        create_anticipation_nodes,
        AnticipationState,
    )

    # Add to your LangGraph StateGraph
    nodes = create_anticipation_nodes(layer)
    graph.add_node("inject_anticipations", nodes.inject)
    graph.add_node("register_event", nodes.register_event)
    graph.add_node("consolidate", nodes.consolidate)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

from ..layer import AnticipationLayer
from ..models import Horizon

logger = logging.getLogger(__name__)


class AnticipationState(TypedDict, total=False):
    """State extension for LangGraph graphs with anticipation support."""
    # The anticipation context block, injected before the LLM call
    anticipation_context: str
    # Events to register (populated by tool calls or observations)
    pending_events: list[str]
    # Consolidation results from the last idle cycle
    consolidation_summary: dict
    # Whether anticipations are stale and need refresh
    needs_refresh: bool


@dataclass
class AnticipationNodes:
    """
    LangGraph-compatible node functions for the Anticipation Layer.

    Each method is a node function that can be added to a StateGraph.
    """

    layer: AnticipationLayer

    def inject(self, state: dict) -> dict:
        """
        Node: Inject relevant anticipations into the state.

        Place this node BEFORE your LLM call node. It reads the
        current query/messages from state and adds anticipation context.

        Expected state keys:
            - messages: list of messages (last user message is used as query)
            OR
            - query: string query

        Adds to state:
            - anticipation_context: formatted anticipation block
        """
        # Extract query from state
        query = state.get("query", "")
        if not query and "messages" in state:
            messages = state["messages"]
            for msg in reversed(messages):
                content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                if content:
                    query = content
                    break

        if not query:
            return {"anticipation_context": ""}

        context = self.layer.get_context(query)
        logger.debug(f"Injected anticipation context ({len(context)} chars)")
        return {"anticipation_context": context}

    def register_event(self, state: dict) -> dict:
        """
        Node: Register pending events and check for invalidations.

        Place this node AFTER tool execution or observation steps.

        Expected state keys:
            - pending_events: list of event description strings

        Adds to state:
            - pending_events: [] (cleared after processing)
            - needs_refresh: True if any anticipations were invalidated
        """
        events = state.get("pending_events", [])
        any_invalidated = False

        for event in events:
            invalidated = self.layer.register_event(event)
            if invalidated:
                any_invalidated = True
                logger.info(
                    f"Event '{event[:50]}...' invalidated "
                    f"{len(invalidated)} anticipation(s)"
                )

        return {
            "pending_events": [],
            "needs_refresh": any_invalidated,
        }

    async def consolidate(self, state: dict) -> dict:
        """
        Node: Run idle consolidation.

        Place this in a conditional branch that triggers during idle periods.

        Adds to state:
            - consolidation_summary: dict with consolidation results
            - needs_refresh: False
        """
        # Build context from state
        context = state.get("anticipation_context", "")
        summary = await self.layer.consolidate(current_context=context)

        return {
            "consolidation_summary": summary,
            "needs_refresh": False,
        }

    def should_consolidate(self, state: dict) -> str:
        """
        Conditional edge: decide whether to consolidate or proceed.

        Usage in graph:
            graph.add_conditional_edges(
                "some_node",
                nodes.should_consolidate,
                {"consolidate": "consolidate_node", "proceed": "next_node"}
            )
        """
        if state.get("needs_refresh", False):
            return "consolidate"
        return "proceed"


def create_anticipation_nodes(
    layer: AnticipationLayer,
) -> AnticipationNodes:
    """
    Factory function to create LangGraph-compatible nodes.

    Args:
        layer: Initialized AnticipationLayer instance.

    Returns:
        AnticipationNodes with inject, register_event, consolidate methods.

    Example:
        layer = AnticipationLayer("./anticipations")
        nodes = create_anticipation_nodes(layer)

        graph = StateGraph(MyState)
        graph.add_node("inject_anticipations", nodes.inject)
        graph.add_node("llm_call", call_llm)
        graph.add_node("register_events", nodes.register_event)

        graph.add_edge(START, "inject_anticipations")
        graph.add_edge("inject_anticipations", "llm_call")
        graph.add_edge("llm_call", "register_events")
        graph.add_conditional_edges(
            "register_events",
            nodes.should_consolidate,
            {"consolidate": "consolidate", "proceed": END}
        )
    """
    return AnticipationNodes(layer=layer)


def build_anticipation_prompt_injection(anticipation_context: str) -> str:
    """
    Helper to format anticipation context for insertion into an LLM prompt.

    This wraps the anticipation context in clear delimiters so the LLM
    knows this is pre-computed temporal awareness, not part of the user query.

    Args:
        anticipation_context: Raw context from layer.get_context()

    Returns:
        Formatted string for prompt injection.
    """
    if not anticipation_context:
        return ""

    return f"""<temporal_awareness>
The following anticipations were pre-computed by your Anticipation Layer.
Use them to inform your decisions — they represent your awareness of 
likely future developments. Do not repeat them to the user unless relevant.

{anticipation_context}
</temporal_awareness>"""
