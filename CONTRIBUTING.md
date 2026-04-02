# Contributing to Anticipation Layer

This is an early-stage research project. We welcome all forms of contribution:

## Ideas & Discussion

- Open an **Issue** to discuss new mechanisms, edge cases, or theoretical questions
- The concept is still evolving — your perspective matters

## Code

1. Fork the repo
2. Create a branch: `git checkout -b feature/your-idea`
3. Write tests for new functionality
4. Run `ruff check .` and `pytest`
5. Open a Pull Request

## Areas We Need Help

- **Semantic similarity**: Better similarity functions beyond keyword overlap
- **LLM integration**: Generation functions for Claude, GPT, local models
- **Benchmarks**: Designing experiments that measure decision quality with/without anticipation
- **Calibration**: Tools to measure and improve confidence score accuracy
- **Self-fulfilling loop detection**: Mechanisms to detect when anticipations bias agent behavior
- **Multi-agent**: How should anticipations be shared across agents?

## Research Directions

- Formal connection to predictive coding / free energy principle
- Optimal decay parameters for different domains
- Context window budget optimization
- Integration patterns with LangGraph, CrewAI, AutoGen
