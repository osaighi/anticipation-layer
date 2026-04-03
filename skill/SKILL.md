---
name: anticipation-layer
description: "Persistent temporal awareness for AI agents. This skill gives you the ability to anticipate future events, risks, and opportunities by maintaining structured prediction files organized by time horizon (short/medium/long term). Use this skill whenever working on a project over multiple sessions, managing tasks with deadlines, making strategic decisions, planning work, debugging recurring issues, or anytime continuity and foresight would improve outcomes. Also trigger when the user mentions 'anticipate', 'predict', 'what could go wrong', 'risks', 'plan ahead', 'future', or asks you to think proactively about upcoming challenges. This skill should be active in the background for any long-running project work."
---

# Anticipation Layer

Persistent temporal awareness through structured future prediction files.

## Core Principle

**Pre-reason about the future during idle moments. Inject those predictions as context at action time.** This turns expensive real-time reasoning into a cheap file read.

## When This Skill Activates

- Starting or resuming work on a project
- Making decisions with future consequences
- After significant events that could change the trajectory
- When the user asks about risks, plans, or what could go wrong
- Periodically during long work sessions (self-trigger consolidation)

## Directory Structure

All anticipation data lives in `.anticipations/` at the project root:

```
.anticipations/
├── short_term.md        # 1-7 days ahead
├── medium_term.md       # 1-3 months ahead
├── long_term.md         # 6-12 months ahead
├── meta.json            # Timestamps, stats, decay params
└── archive/             # Past anticipations for learning
```

## Step 1: Initialize

On first activation, check if `.anticipations/` exists. If not, run:

```bash
python /path/to/skill/scripts/init.py
```

This creates the directory structure with empty template files.

If `.anticipations/` already exists, read `meta.json` to check when the last update happened. If stale (see decay rules below), trigger a refresh.

## Step 2: Read Anticipations

At the start of every significant interaction, read the anticipation files to inform your reasoning. You don't need to mention them explicitly to the user unless they're directly relevant.

**How to read**: Scan each horizon file. Focus on entries with `status: active` and high weight. Use them as background context — like a mental model of what's coming.

## Step 3: Generate Anticipations

When generating or updating anticipations, think like a seasoned strategist. For each horizon, produce 3-5 entries following this format:

```markdown
### [ANT-YYYYMMDD-NNN] Title
- **Status**: active | expired | invalidated | realized
- **Created**: ISO timestamp
- **Expires**: ISO timestamp
- **Confidence**: 0.0-1.0 (calibrate honestly — don't default to 0.5)
- **Category**: risk | opportunity | neutral
- **Impact**: low | medium | high | critical
- **Domain**: area this relates to (e.g., "backend", "deployment", "team")

**Prediction**: Clear, specific statement about what might happen. Be concrete — "API migration may break 3 downstream services if not tested by Friday" not "there might be issues."

**Suggested actions**:
1. Concrete action the user could take
2. Another concrete action

**Dependencies**: Links to other anticipations if relevant
```

### Generation Guidelines

- **Be specific, not vague.** Every prediction should be falsifiable.
- **Calibrate confidence honestly.** Use the full range. 0.3 for hunches, 0.9 for near-certainties.
- **Balance risks and opportunities.** Don't be only pessimistic.
- **Consider second-order effects.** If X happens, what does that cause?
- **Make it actionable.** If nothing can be done about it, don't anticipate it.

### Horizon-Specific Guidance

**Short term (1-7 days)**: Tactical. Deployment risks, upcoming deadlines, blockers, immediate team issues. High specificity, high confidence expected.

**Medium term (1-3 months)**: Strategic. Project trajectory, resource constraints, technical debt accumulation, dependency risks. Moderate specificity.

**Long term (6-12 months)**: Directional. Architecture decisions ripple effects, market shifts, team scaling needs, technology evolution. Lower confidence is normal.

## Step 4: Update Anticipations

Four update mechanisms, inspired by the human brain's predictive coding system:

### 4a. Invalidation (Prediction Error Signal)

When an event contradicts a prediction, mark it `invalidated` and note what happened. This is the most important mechanism — it fires on "surprise."

After any significant action or observation, quickly scan active anticipations:
- Does this event contradict any prediction? → Invalidate
- Does this event confirm a prediction? → Mark realized, boost confidence of related predictions
- No match? → Do nothing (this is the common case — be efficient)

### 4b. Temporal Decay

Each horizon has a TTL. Run `scripts/check_decay.py` to find stale entries:

| Horizon | TTL | Refresh frequency |
|---------|-----|-------------------|
| Short term | 48h | Daily |
| Medium term | 2 weeks | Weekly |
| Long term | 2 months | Monthly |

Stale entries get regenerated with fresh context.

### 4c. Cascading Reappraisal

If a major event invalidates >30% of short-term anticipations, also reappraise medium-term. If >50% of medium-term changes, reappraise long-term. This mimics how a shock propagates through your mental model.

### 4d. Idle Consolidation

When there's a natural pause in work (end of a task, waiting for build, session end), run a consolidation:

1. Archive non-active anticipations
2. Reinforce surviving predictions (small confidence boost)
3. Look for patterns in invalidations
4. Generate new anticipations if gaps exist
5. Update `meta.json` timestamps

Run: `python /path/to/skill/scripts/consolidate.py .anticipations/`

## Step 5: Inject Into Reasoning

When making decisions, don't just answer the immediate question. Weigh it against active anticipations:

- If a user asks "should we deploy today?" and you have a short-term risk about an untested migration — surface it.
- If a user is planning Q3 work and you have a medium-term prediction about budget constraints — factor it in.
- If relevant, mention the anticipation explicitly: "Based on what I've been tracking, [prediction] is worth considering here."

**Don't overwhelm.** Only surface anticipations that are directly relevant to the current task. The rest stays as background awareness.

## Meta.json Schema

```json
{
  "initialized": "2026-04-02T10:00:00Z",
  "last_consolidation": "2026-04-02T14:30:00Z",
  "last_refresh": {
    "short_term": "2026-04-02T14:30:00Z",
    "medium_term": "2026-03-28T10:00:00Z",
    "long_term": "2026-03-01T10:00:00Z"
  },
  "stats": {
    "total_generated": 24,
    "total_invalidated": 5,
    "total_realized": 8,
    "total_expired": 3
  }
}
```

## Scripts Reference

| Script | Purpose | When to run |
|--------|---------|-------------|
| `scripts/init.py` | Initialize `.anticipations/` directory | First activation |
| `scripts/check_decay.py` | Find stale/expired anticipations | Start of session |
| `scripts/consolidate.py` | Archive, reinforce, rebalance | End of task or session |
| `scripts/metrics.py` | Show realization rate, calibration | On user request |

## Key Behaviors

1. **Be invisible most of the time.** Anticipations are background awareness, not conversation topics.
2. **Surface predictions only when relevant.** Don't dump your anticipation state on the user.
3. **Update continuously.** Every significant event is a potential invalidation signal.
4. **Be honest about uncertainty.** Low confidence is fine. Overconfidence is dangerous.
5. **Learn from mistakes.** Track invalidations and realized predictions to improve over time.

## For Deeper Understanding

Read `references/concept.md` for the full theoretical foundation including the neuroscience behind each update mechanism.
