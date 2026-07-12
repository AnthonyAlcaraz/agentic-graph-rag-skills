# Chapter 4 — Memory

- **Skills folder:** `skills/memory/` (7 skills)
- **Notebook:** `notebooks/ch4-memory.ipynb`
- **Prev:** [Chapter 3](./03-knowledge-representation.md) &nbsp;|&nbsp; **Next:** [Chapter 5](./05-reasoning-planning.md)

## Role in the architecture

Makes the vertical graph durable and temporal. Bi-temporal edges track valid-time vs system-time, Graphiti-style incremental update avoids full re-processing, hierarchical memory tiers hot/warm/cold, and RRF fuses four retrieval channels.

## In the running DevOps investigation

Prior `checkout-service` incidents are recalled with their time context; new telemetry updates only the changed subgraph; the current incident is consolidated from noisy episodes into durable knowledge.

## Skills

| Skill | What it does | CLI |
|-------|--------------|-----|
| `bi-temporal-edge` | Bi-temporal edge primitive for agentic graph memory. | `python skills/memory/bi-temporal-edge/cli.py --help` |
| `graphiti-incremental-update` | Graphiti (Zep) incremental-update pattern (Ch4). | `python skills/memory/graphiti-incremental-update/cli.py --help` |
| `hierarchical-memory` | Three-tier hierarchical memory (Letta / MemGPT pattern) — | `python skills/memory/hierarchical-memory/cli.py --help` |
| `hindsight-epistemic-classifier` | Classify facts into HINDSIGHT's 4 epistemic networks (Latimer et al. | `python skills/memory/hindsight-epistemic-classifier/cli.py --help` |
| `letta-failure-modes` | Reviewer skill: diagnose an agent's memory architecture against the 8 Letta Leaderboard failure modes (Ch4). | `python skills/memory/letta-failure-modes/cli.py --help` |
| `memory-consolidation` | Consolidation pipeline — | `python skills/memory/memory-consolidation/cli.py --help` |
| `rrf-hybrid-retrieval` | Reciprocal Rank Fusion (RRF) hybrid retrieval across 4 parallel channels — | `python skills/memory/rrf-hybrid-retrieval/cli.py --help` |

## Run it

```bash
# every skill self-documents
python skills/memory/bi-temporal-edge/cli.py --help

# the chapter walkthrough against moto-mocked AWS
jupyter notebook notebooks/ch4-memory.ipynb
```
