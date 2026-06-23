# agentic-graph-rag-skills

Companion repo for *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz). Practical, multi-harness skills + AWS-serverless DevOps notebooks distilled from chapters Ch3-Ch7 of the book.

> Read the book for the theory. Run these skills with your coding agent for the practice.

## What's here

- **`skills/<chapter-slug>/<skill-slug>/`** — Osmani-format `SKILL.md` files + hand-rolled Python CLIs. Each skill is one architectural primitive from one chapter of the book. Multi-harness: works in Claude Code, Cursor, Gemini CLI, Windsurf, OpenCode, and from cron / CI / scripts.
- **`notebooks/`** — Jupyter notebooks demonstrating each skill against a fictional AWS DevOps scenario. Real boto3 code, mocked AWS via [`moto`](https://github.com/getmoto/moto) so notebooks run with zero credentials. Swap the `@mock_aws` decorator for your real account to deploy.
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

| Chapter | Skills folder | Status |
|---------|---------------|--------|
| Ch3 — Knowledge Representation | `skills/knowledge-representation/` | pending Phase 1 |
| **Ch4 — Memory** | **`skills/memory/`** | **shipped — 6 skills** (`bi-temporal-edge`, `graphiti-incremental-update`, `hierarchical-memory`, `hindsight-epistemic-classifier`, `letta-failure-modes`, `rrf-hybrid-retrieval`) |
| Ch5 — Reasoning & Planning | `skills/reasoning-planning/` | pending Phase 1 |
| **Ch6 — Tool Orchestration** | **`skills/tool-orchestration/`** | **shipped — 2 skills** (`rag-mcp-tool-selection`, `mcp-gateway-two-meta-tools`) |
| **Ch7 — Self-Evolution & Evaluation** | **`skills/self-evolution/`** | **shipped — 1 skill** (`execution-graph`) |

Ch1 (Crisis) and Ch2 (Architecture) are book-only narrative chapters — no skills extracted.

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
