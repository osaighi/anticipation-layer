# 🔮 Anticipation Layer

**Persistent Temporal Awareness for AI Agents**

> An agent that has already thought about the future makes better decisions in the present, with no additional cognitive cost at the time of action.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## What is this?

The **Anticipation Layer** is an architectural component for AI agent systems that introduces persistent temporal awareness. Unlike conventional planning modules that operate *in the moment* in response to a task, the Anticipation Layer continuously maintains a structured representation of possible futures — organized by time horizons — and injects it as passive context into every agent interaction.

Current AI agents suffer from a temporal paradox:

- **Reactive agents** respond to stimuli without considering the future. Fast but shortsighted.
- **Planning agents** anticipate, but only within the scope of an explicit task. Their horizon is bounded by the current request.
- **No agent** maintains a persistent, structured representation of the future between interactions.

Humans operate differently. A manager doesn't wait to be asked "what's going to happen next week?" — they already know, because their brain continuously maintains a predictive model of the future across multiple time scales. The Anticipation Layer bridges this gap.

## Key Concepts

### Pre-reasoned Context

Instead of reasoning about the future at every request (expensive), the agent **pre-computes anticipations** during idle time and stores them. At action time, they are simply loaded as context — turning a costly reasoning step into a cheap file read.

### Three Time Horizons

```
anticipations/
├── short_term.json    # 1-7 days    — tactical decisions
├── medium_term.json   # 1-3 months  — strategic planning
└── long_term.json     # 6-12 months — vision & direction
```

Each horizon has its own decay rate, refresh frequency, and update dynamics.

### Four Bio-Inspired Update Mechanisms

Inspired by how the human brain maintains and updates its predictive models:

| Mechanism | Brain Analogy | When it fires |
|-----------|--------------|---------------|
| **Invalidation** | Prediction error signal (Friston) | Reality contradicts a prediction |
| **Temporal Decay** | Ebbinghaus forgetting curve | Anticipation ages past its TTL |
| **Cascading Reappraisal** | Shock-triggered chain revision | Major event invalidates >30% of a horizon |
| **Idle Consolidation** | Sleep-dependent memory replay | Agent has no active requests |

## Architecture

```
┌──────────────────────────────────────────────────┐
│                   AGENT CORE                     │
│  ┌───────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ Perception│  │Reasoning │  │   Action     │   │
│  └─────┬─────┘  └────┬─────┘  └──────┬───────┘   │
│        │             │               │           │
│  ┌─────┴─────────────┴───────────────┴─────┐     │
│  │         CONTEXT ASSEMBLY                │     │
│  │  (injects anticipations as passive      │     │
│  │   context into every request)           │     │
│  └─────────────────┬───────────────────────┘     │
│                    │                             │
│  ┌─────────────────┴───────────────────────┐     │
│  │        ANTICIPATION LAYER               │     │
│  │                                         │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │     │
│  │  │  Short   │ │  Medium  │ │  Long    │ │     │
│  │  │  term    │ │  term    │ │  term    │ │     │
│  │  │ (1-7d)   │ │ (1-3mo)  │ │ (6-12mo) │ │     │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ │     │
│  │       │            │            │       │     │
│  │  ┌────┴────────────┴────────────┴────┐  │     │
│  │  │       UPDATE ENGINE               │  │     │
│  │  │  (invalidation, decay, cascade)   │  │     │
│  │  └───────────────────────────────────┘  │     │
│  └─────────────────────────────────────────┘     │
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │              MEMORY LAYER                │    │
│  └──────────────────────────────────────────┘    │
└──────────────────────────────────────────────────┘
```

## Quick Start

```bash
pip install anticipation-layer
# Optional: YAML config support
pip install anticipation-layer[config]
# Optional: LLM generation (Claude / OpenAI)
pip install anticipation-layer[llm]
```

```python
import asyncio
from anticipation_layer import AnticipationLayer, Horizon, Category, Impact
from anticipation_layer.generators import ClaudeGenerator

# Initialize with a config file (optional)
generator = ClaudeGenerator(api_key="sk-ant-...")
layer = AnticipationLayer(
    storage_dir="./anticipations",
    generate_fn=generator.generate,
    config_path="anticipation_config.yaml",  # optional
)

# Add an anticipation manually
layer.add(
    prediction="Thursday's deployment may fail if hotfix #342 is not merged by Wednesday.",
    horizon=Horizon.SHORT_TERM,
    category=Category.RISK,
    impact=Impact.HIGH,
    confidence=0.75,
)

# Get relevant anticipations for a request (cheap: just a file read + filter)
context = layer.get_context("Should we proceed with Thursday's deployment?")

# Register an event (triggers invalidation check)
layer.register_event("Hotfix #342 was merged successfully")

# Run idle consolidation (generates new anticipations via LLM, archives old ones)
asyncio.run(layer.consolidate(current_context="Sprint ends Friday. Q2 budget at 87%."))

# Inspect all active anticipations
print(layer.status())

# Performance metrics
print(layer.metrics())
```

## Anticipation Format

Each anticipation is a structured entry:

```yaml
- id: "ant-20260402-001"
  created: "2026-04-02T10:30:00Z"
  expires: "2026-04-09T10:30:00Z"
  confidence: 0.75
  category: "risk"              # risk | opportunity | neutral
  domain: "project-alpha"
  horizon: "short_term"         # short_term | medium_term | long_term
  prediction: "Thursday's deployment may fail if hotfix #342 is not merged by Wednesday."
  impact: "high"                # low | medium | high | critical
  suggested_actions:
    - "Follow up with the backend team on hotfix #342"
    - "Prepare a rollback plan"
  status: "active"              # active | expired | invalidated | realized
```

## Configuration

Pass `config_path` to `AnticipationLayer` to load settings from a YAML file
(requires `pip install anticipation-layer[config]`):

```python
layer = AnticipationLayer(storage_dir="./anticipations", config_path="anticipation_config.yaml")
```

```yaml
# anticipation_config.yaml
horizons:
  short_term:
    range_days: [1, 7]
    ttl_hours: 48
    decay_lambda: 0.3
    refresh: "daily"
  medium_term:
    range_days: [30, 90]
    ttl_hours: 336        # 2 weeks
    decay_lambda: 0.05
    refresh: "weekly"
  long_term:
    range_days: [180, 365]
    ttl_hours: 1440       # 2 months
    decay_lambda: 0.01
    refresh: "monthly"

update_engine:
  invalidation_threshold: 0.5   # similarity threshold for prediction error
  cascade_threshold_short: 0.3  # 30% invalidation triggers medium reappraisal
  cascade_threshold_medium: 0.5 # 50% invalidation triggers long reappraisal
  weight_floor: 0.3             # below this weight, flag for refresh

context_injection:
  top_k: 10
  min_relevance: 0.1
  max_tokens: 500               # max context budget for anticipations

consolidation:
  idle_timeout_seconds: 300     # trigger after 5 min of inactivity
  max_new_anticipations: 5      # cap proactive generation per cycle
```

Without a config file, all values default to the values above.

## Documentation

- [Concept Paper](docs/concept.md) — Full theoretical foundation
- [Architecture Deep Dive](docs/architecture.md) — Technical details
- [Update Mechanisms](docs/update_mechanisms.md) — The four bio-inspired mechanisms explained
- [Integration Guide](docs/integration.md) — How to plug this into your agent

## How It's Different

| Feature | Classical Planning | Proactive Agents | **Anticipation Layer** |
|---|---|---|---|
| Trigger | Explicit task | Detected event | **Permanent (idle + events)** |
| Persistence | Task duration | Session | **Persistent across sessions** |
| Time horizons | Single (task) | Short term | **Short / Medium / Long term** |
| Cost at action time | High (plans each time) | Medium | **Low (pre-reasoned)** |
| Update mechanism | N/A | Reactive | **4 bio-inspired mechanisms** |
| Learning | No | Limited | **Full feedback loop** |

## Roadmap

- [x] Concept formalization
- [x] Core library (`AnticipationLayer`, `UpdateEngine`, `ContextAssembly`)
- [x] File-based storage backend (JSON)
- [x] Similarity functions (keyword, TF-IDF, embedding-based)
- [x] LLM-powered generation (Claude — async + sync)
- [x] LLM-powered invalidation checking
- [x] LangGraph integration (nodes, state, conditional edges)
- [x] YAML configuration (`config_path` param, `[config]` extra)
- [ ] OpenAI generator
- [ ] CrewAI integration
- [ ] Benchmarks: decision quality with/without anticipation
- [ ] Calibration toolkit (confidence score accuracy)
- [ ] Self-fulfilling loop detection
- [ ] Vector DB storage backend
- [ ] Multi-agent shared anticipations
- [ ] MCP server (expose anticipations as a tool)

## Contributing

This is an early-stage research project. Contributions, ideas, and discussions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

## References

- Friston, K. (2005). *A theory of cortical responses*. Philosophical Transactions of the Royal Society B.
- Rao, R. P., & Ballard, D. H. (1999). *Predictive coding in the visual cortex*. Nature Neuroscience.
- Diekelmann, S., & Born, J. (2010). *The memory function of sleep*. Nature Reviews Neuroscience.
- Schacter, D. L., Addis, D. R., & Buckner, R. L. (2007). *Remembering the past to imagine the future*. Nature Reviews Neuroscience.
- Ebbinghaus, H. (1885). *Über das Gedächtnis*.

## License

MIT — see [LICENSE](LICENSE).
