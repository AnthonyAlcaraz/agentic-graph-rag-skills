# agentic-graph-rag-skills

Companion repo for *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz). Practical, multi-harness skills + AWS-serverless DevOps notebooks distilled from all eight chapters (Ch1-Ch8) of the book. **45 skills across 8 chapters, plus one deep pedagogical notebook per chapter.**

> Read the book for the theory. Run these skills with your coding agent for the practice.

> **AI agents:** read [`AGENTS.md`](./AGENTS.md) first — it is this repo's machine-readable reading contract (how to summarize it, the key claims you may cite, what not to invent, and how to discover + invoke a skill).

## What's here

- **`skills/<chapter-slug>/<skill-slug>/`** — Osmani-format `SKILL.md` files + hand-rolled Python CLIs. Each skill is one architectural primitive from one chapter of the book. Multi-harness: works in Claude Code, Cursor, Gemini CLI, Windsurf, OpenCode, and from cron / CI / scripts.
- **`notebooks/`** — Jupyter notebooks demonstrating each skill against a fictional AWS DevOps scenario. Real boto3 code, mocked AWS via [`moto`](https://github.com/getmoto/moto) so notebooks run with zero credentials. Swap the `@mock_aws` decorator for your real account to deploy.
- **`docs/`** — The documentation layer: [`docs/README.md`](./docs/README.md) is the architecture overview + reading map, and one page per chapter (`docs/0N-*.md`) ties that chapter's skills to the architecture and to the running DevOps example. Start here to navigate the 45 skills.
- **`PLAN.md`** — The GSD spec that drives chapter conversion. Vertical-slice ordering, locked decisions, verification gates.

## Quickstart

```bash
git clone https://github.com/AnthonyAlcaraz/agentic-graph-rag-skills.git
cd agentic-graph-rag-skills
pip install -r requirements.txt

# Try the spike skill — RAG-MCP tool selection (Ch5/Ch6)
python skills/tool-orchestration/rag-mcp-tool-selection/cli.py --help
python skills/tool-orchestration/rag-mcp-tool-selection/cli.py benchmark
```

To run the notebook (the DevOps latency-investigation worked example):

```bash
jupyter notebook notebooks/spike-a-rag-mcp-tool-selection.ipynb
```

For the optional Anthropic-API cell, set `ANTHROPIC_API_KEY` in your environment. The notebook skips the cell gracefully if the key is absent.

## DevOps use case

The notebooks all act through a single running scenario: a DevOps agent investigating latency in the checkout API of a fictional AWS account (`123456789012`). The scenario is introduced in book Chapter 5/6 and threaded through subsequent chapters. Each chapter's skills exercise different parts of the investigation — tool selection, memory of prior incidents, reasoning over the call graph, evaluation of remediation actions.

To run any notebook against your own AWS account: remove the `@mock_aws` decorator and the `AWS_*` environment variables. The boto3 code is unchanged.

## Chapter coverage

All eight chapters ship skills. Each chapter also has one deep pedagogical notebook (`notebooks/chN-*.ipynb`) that threads the running DevOps latency-investigation scenario against `moto`-mocked AWS.

| Chapter | Skills folder | Notebook | Skills |
|---------|---------------|----------|--------|
| **Ch1 — Defining Agentic AI** | **`skills/crisis/`** | `notebooks/ch1-defining-agentic-ai.ipynb` | **5** — `context-failure-classifier`, `enterprise-readiness-scorer`, `agent-constraint-triangle-scorer`, `workflow-agent-spectrum-classifier`, `vector-vs-graph-retrieval-selector` |
| **Ch2 — Architecture Foundations** | **`skills/architecture/`** | `notebooks/ch2-architecture-foundations.ipynb` | **3** — `dual-graph-router`, `harness-node-splitter`, `eight-pillar-readiness-map` |
| **Ch3 — Knowledge Representation** | **`skills/knowledge-representation/`** | `notebooks/ch3-knowledge-representation.ipynb` | **6** — `graph-model-selector`, `three-graph-router`, `schema-pattern-selector`, `homoiconic-meta-schema`, `knowledge-organization-classifier`, `capability-authorization-gate` |
| **Ch4 — Memory** | **`skills/memory/`** | `notebooks/ch4-memory.ipynb` | **7** — `bi-temporal-edge`, `graphiti-incremental-update`, `hierarchical-memory`, `hindsight-epistemic-classifier`, `letta-failure-modes`, `memory-consolidation`, `rrf-hybrid-retrieval` |
| **Ch5 — Reasoning & Planning** | **`skills/reasoning-planning/`** | `notebooks/ch5-reasoning-planning.ipynb` | **5** — `pipeline-architecture-selector`, `investigation-dag-planner`, `loop-pipeline-router`, `constraint-guided-plan-validator`, `parallel-reconcile-merge` |
| **Ch6 — Tool Orchestration** | **`skills/tool-orchestration/`** | `notebooks/ch6-tool-orchestration.ipynb` | **7** — `rag-mcp-tool-selection`, `mcp-gateway-two-meta-tools`, `skill-quality-evaluator`, `information-flow-control-gate`, `draft-tool-trust-verifier`, `hierarchical-orchestration-router`, `federated-context-governance` |
| **Ch7 — Self-Evolution & Evaluation** | **`skills/self-evolution/`** | `notebooks/ch7-self-evolution.ipynb` | **7** — `execution-graph`, `four-layer-eval-cascade`, `evolution-taxonomy-classifier`, `intervention-selector`, `semantic-backprop-attributor`, `graduated-validation-protocol`, `xskill-self-improving-object` |
| **Ch8 — Optimization** | **`skills/optimization/`** | `notebooks/ch8-optimization.ipynb` | **5** — `model-routing-selector`, `cost-performance-scorer`, `subgraph-access-control`, `schema-evolution-migrator`, `kv-cache-latency-budgeter` |

Total: **45 skills, 8 pedagogical notebooks.** The Ch1 folder is named `skills/crisis/` for historical reasons (the chapter opens on the crisis of enterprise agentic AI); it is the Chapter 1 folder. The six original `notebooks/spike-*.ipynb` seam-validation notebooks are retained.

## How a skill is structured

Each skill folder contains:

- `SKILL.md` — Osmani 7-section anatomy (frontmatter / Overview / When to Use / When NOT to Use / Process / Rationalizations / Red Flags / Non-Negotiable Verification) plus a Security Posture section and a Source Attribution line back to the chapter.
- `lib.py` — pure-Python implementation. Production swaps (e.g. embedding models) are documented as TODOs at the relevant seam.
- `cli.py` — argparse CLI. `--help` prints the SKILL.md description verbatim. Every Process step has a corresponding subcommand or flag.
- Asset files (JSON, YAML, sample data) as needed.

## License

MIT. See `LICENSE`.

## Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz / forthcoming). Each skill cites its source chapter in `SKILL.md` frontmatter. The skills are operational tooling; the book carries the architectural IP.

## Contributing

Spec-driven: read `PLAN.md` first. The vertical-slice ordering names what's expected at each phase. New skills should mirror the structure of `skills/tool-orchestration/rag-mcp-tool-selection/` and pass `python cli.py --help` + a benchmark battery + at least one notebook cell exercising the skill against `moto`-mocked AWS.
