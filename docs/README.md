# Documentation — agentic-graph-rag-skills

The operational documentation layer for the [*Agentic Graph RAG*](https://www.oreilly.com/library/view/agentic-graphrag/9798341623163/) (O'Reilly, by Anthony Alcaraz and Sam Julien) companion repo:
**50 skills across 8 chapters, one pedagogical notebook per chapter, six seam-validation spikes.**
The book carries the theory; this repo is the practice; these docs are the map that ties every
component to the architecture and to one running example.

## The organizing idea: two graphs + one harness

Every skill in the repo is a primitive that lives on one of three structures introduced in Chapter 2:

- **Vertical knowledge graph** — *what is true* (services, dependencies, owners, incidents). Chapters 3-4 build and maintain it.
- **Horizontal workflow graph** — *what the agent does* (a DAG of constrained nodes). Chapters 5-6 plan and execute it.
- **The harness** — the boundary that splits work into nodes by tool surface. Chapter 7 lets it improve itself; Chapter 8 makes it cheap.

## The one running example

Every chapter notebook exercises the **same** scenario: a DevOps agent investigating high latency
on `checkout-service` in a fictional AWS account (`123456789012`), with real boto3 code against
`moto`-mocked AWS so notebooks run with zero credentials. Each chapter works a different part of the
same investigation, so the components are never demonstrated in isolation.

## Flow of ideas — the eight chapters

| # | Chapter | `skills/` | n | Doc | Notebook |
|---|---------|-----------|---|-----|----------|
| 1 | Defining Agentic AI | `crisis/` | 5 | [01-defining-agentic-ai](./01-defining-agentic-ai.md) | `notebooks/ch1-defining-agentic-ai.ipynb` |
| 2 | Architecture Foundations | `architecture/` | 3 | [02-architecture-foundations](./02-architecture-foundations.md) | `notebooks/ch2-architecture-foundations.ipynb` |
| 3 | Knowledge Representation | `knowledge-representation/` | 8 | [03-knowledge-representation](./03-knowledge-representation.md) | `notebooks/ch3-knowledge-representation.ipynb` |
| 4 | Memory | `memory/` | 8 | [04-memory](./04-memory.md) | `notebooks/ch4-memory.ipynb` |
| 5 | Reasoning & Planning | `reasoning-planning/` | 6 | [05-reasoning-planning](./05-reasoning-planning.md) | `notebooks/ch5-reasoning-planning.ipynb` |
| 6 | Tool Orchestration | `tool-orchestration/` | 8 | [06-tool-orchestration](./06-tool-orchestration.md) | `notebooks/ch6-tool-orchestration.ipynb` |
| 7 | Self-Evolution & Evaluation | `self-evolution/` | 7 | [07-self-evolution](./07-self-evolution.md) | `notebooks/ch7-self-evolution.ipynb` |
| 8 | Optimization | `optimization/` | 5 | [08-optimization](./08-optimization.md) | `notebooks/ch8-optimization.ipynb` |

**Total: 50 skills.** Read a row as "this chapter deepens *that* part of the Chapter-2 foundation."

## How every skill is structured

Each `skills/<chapter>/<skill>/` folder is a self-contained, multi-harness primitive:

- **`SKILL.md`** — 7-section anatomy (Overview / When to Use / When NOT / Process / Rationalizations / Red Flags / Non-Negotiable Verification) + Security Posture + Source Attribution to the chapter.
- **`lib.py`** — pure-Python implementation; production swaps flagged as TODOs at the seam.
- **`cli.py`** — argparse CLI; `--help` prints the SKILL.md description; every Process step maps to a subcommand or flag. Runs in Claude Code, Cursor, Gemini CLI, Windsurf, OpenCode, or from cron / CI.

## Source manuscripts

The source book manuscripts the skills were distilled from live in a local, git-ignored
`chapter-content/` folder (the book prose is not redistributed in this public repo). Each skill's
`SKILL.md` cites its source chapter; the book carries the architectural IP.
