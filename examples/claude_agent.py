"""
Example: Full Claude-powered agent with Anticipation Layer.

This demonstrates an AI project manager agent that:
1. Generates anticipations from project context
2. Injects them into every interaction
3. Updates them as events unfold
4. Consolidates during idle time

Requires: pip install anticipation-layer[llm]
Set ANTHROPIC_API_KEY in your environment.
"""

import asyncio
import os
import logging
from datetime import datetime

from anticipation_layer import AnticipationLayer, Horizon, Category, Impact
from anticipation_layer.generators.claude import ClaudeGenerator
from anticipation_layer.integrations.langgraph import build_anticipation_prompt_injection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    # ── Setup ─────────────────────────────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Set ANTHROPIC_API_KEY to run this example.")
        return

    generator = ClaudeGenerator(api_key=api_key)
    layer = AnticipationLayer(
        storage_dir="./project_anticipations",
        generate_fn=generator.generate,
    )

    # ── Step 1: Bootstrap anticipations from project context ──────
    project_context = """
    Project: Customer Portal v2.0 Rewrite
    Status: Sprint 14 of 20. Velocity trending down (38 → 31 points).
    Team: 5 engineers (1 on PTO next week), 1 PM, 1 designer.
    Key risks flagged in retro: API migration incomplete, test coverage at 62%.
    Upcoming: Demo to VP of Product on March 15. Go-live target: April 30.
    Budget: 78% consumed with 30% of work remaining.
    Dependencies: Payment service team promised SDK update by March 10.
    Recent events: Senior engineer gave 2-week notice yesterday.
    """

    print("=" * 60)
    print("STEP 1: Generating anticipations from project context...")
    print("=" * 60)

    for horizon in Horizon:
        print(f"\n  Generating {horizon.value}...")
        anticipations = await generator.generate(
            context=project_context,
            horizon=horizon,
            count=3,
        )
        for ant in anticipations:
            layer.add(
                prediction=ant.prediction,
                horizon=horizon,
                category=ant.category,
                impact=ant.impact,
                confidence=ant.confidence,
                domain=ant.domain,
                suggested_actions=ant.suggested_actions,
            )
            print(f"    [{ant.category.value}] {ant.prediction[:70]}... "
                  f"(confidence: {ant.confidence:.0%})")

    # ── Step 2: Show full anticipation state ──────────────────────
    print("\n" + "=" * 60)
    print("STEP 2: Full anticipation state")
    print("=" * 60)
    print(layer.status())

    # ── Step 3: Simulate a user query with anticipation context ───
    print("=" * 60)
    print("STEP 3: Query with anticipation-enriched context")
    print("=" * 60)

    user_query = "Should we commit to the April 30 go-live date in tomorrow's demo?"
    ant_context = layer.get_context(user_query)
    prompt_block = build_anticipation_prompt_injection(ant_context)

    print(f"\nUser query: {user_query}")
    print(f"\nInjected context ({len(ant_context)} chars):")
    print(ant_context)

    # In a real agent, you'd insert prompt_block into the system prompt
    # before calling the LLM. The agent benefits from pre-computed
    # awareness without having to reason about the future in real-time.

    # ── Step 4: Register events and check invalidations ───────────
    print("\n" + "=" * 60)
    print("STEP 4: Registering events...")
    print("=" * 60)

    events = [
        "Payment service team delivered SDK update ahead of schedule on March 8.",
        "Test coverage pushed to 74% after weekend sprint.",
        "VP of Product moved demo to March 20 due to scheduling conflict.",
    ]

    for event in events:
        print(f"\n  Event: {event[:60]}...")
        invalidated = layer.register_event(event)
        if invalidated:
            for ant in invalidated:
                print(f"    ❌ Invalidated: {ant.prediction[:60]}...")
        else:
            print(f"    → No anticipations invalidated")

    # ── Step 5: Run consolidation ─────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 5: Running idle consolidation...")
    print("=" * 60)

    updated_context = project_context + """
    Updates since last cycle:
    - Payment SDK delivered early
    - Test coverage improved to 74%
    - Demo moved to March 20
    """

    summary = await layer.consolidate(current_context=updated_context)
    print(f"\n  Consolidation results:")
    for key, value in summary.items():
        print(f"    {key}: {value}")

    # ── Step 6: Updated state and metrics ─────────────────────────
    print("\n" + "=" * 60)
    print("STEP 6: Updated anticipation state")
    print("=" * 60)
    print(layer.status())

    print("\n" + "=" * 60)
    print("METRICS")
    print("=" * 60)
    metrics = layer.metrics()
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2%}")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
