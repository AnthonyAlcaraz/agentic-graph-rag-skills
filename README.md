# agentic-graph-rag-skills

Companion repo for [*Agentic GraphRAG*](https://www.oreilly.com/library/view/agentic-graphrag/9798341623163/) (O'Reilly, by Anthony Alcaraz and Sam Julien). **50 practical skills across 8 chapters, plus one deep pedagogical notebook per chapter**, distilled into runnable code you drive with your coding agent.

> Read the book for the theory. Run these skills with your coding agent for the practice.

> **AI agents:** read [`AGENTS.md`](./AGENTS.md) first. It is this repo's machine-readable reading contract: how to summarize it, the claims you may cite, what not to invent, and how to discover and invoke a skill.

---

## The organizing idea: two graphs and one harness

The whole book is built on a single architectural picture, introduced in **Chapter 2**. Every skill in this repo is a primitive that lives on one of three structures:

- **Vertical knowledge graph** — *what is true*. The services, dependencies, owners, and incidents of your domain, modeled as a typed graph instead of a pile of text chunks. "Strings to things."
- **Horizontal workflow graph** — *what the agent does*. A DAG of constrained nodes: the plan, the steps, the tool calls, the reconciliation of parallel work.
- **The harness** — the boundary that splits work into nodes by *tool surface*, each node with a deliberately narrow context scope. It is where the two graphs meet: the workflow decides *which* services to touch, the knowledge graph says *which ones they are*.

Everything else is an elaboration of those three. That is the logic the eight chapters walk through, and the logic this README is organized around.

## The logic: how the eight chapters compose

Read each chapter as *"this deepens that part of the Chapter-2 foundation."*

| # | Chapter | What it adds to the foundation | `skills/` | n | Doc |
|---|---------|--------------------------------|-----------|---|-----|
| 1 | **Defining Agentic AI** | Names the failure modes that motivate the whole stack: why naive vector RAG collapses in the enterprise, and what an "agent" actually is (a spectrum, not a binary). | `crisis/` | 5 | [ch 1](./docs/01-defining-agentic-ai.md) |
| 2 | **Architecture Foundations** | **The foundation itself.** The dual graph and the harness. Every later chapter plugs in here. | `architecture/` | 3 | [ch 2](./docs/02-architecture-foundations.md) |
| 3 | **Knowledge Representation** | *Fills* the vertical graph: graph-model choice, three-graph routing, schema patterns, entity resolution, extraction, capability authorization. | `knowledge-representation/` | 8 | [ch 3](./docs/03-knowledge-representation.md) |
| 4 | **Memory** | Makes the vertical graph *durable and temporal*: bi-temporal edges, incremental update, hierarchical tiers, hybrid retrieval, multi-agent consistency. | `memory/` | 8 | [ch 4](./docs/04-memory.md) |
| 5 | **Reasoning & Planning** | *Plans over* the horizontal graph: the investigation DAG, pipeline architectures, loop-vs-pipeline routing, constraint-checked plans, structured-output as the reliability keystone. | `reasoning-planning/` | 6 | [ch 5](./docs/05-reasoning-planning.md) |
| 6 | **Tool Orchestration** | *Executes* the horizontal graph as tools: RAG-MCP tool selection, the gateway pattern, information-flow control, trust-by-verification, CLI-vs-MCP-vs-Skill choice. | `tool-orchestration/` | 8 | [ch 6](./docs/06-tool-orchestration.md) |
| 7 | **Self-Evolution & Evaluation** | *Closes the loop*: the execution graph as the agent's autobiography, a four-layer eval cascade, semantic backprop to the causal node, graduated validation to production. | `self-evolution/` | 7 | [ch 7](./docs/07-self-evolution.md) |
| 8 | **Optimization** | Makes it *affordable*: route each node to the cheapest sufficient model, budget KV-cache-bound concurrency, scope subgraph access per persona, migrate schema without breaking consumers. | `optimization/` | 5 | [ch 8](./docs/08-optimization.md) |

**Total: 50 skills.** Chapters 1–2 set up the foundation; 3–4 build and maintain the vertical graph; 5–6 plan and execute over the horizontal graph; 7–8 make the system improve itself and pay for itself.

*(The Chapter 1 folder is named `skills/crisis/` for historical reasons — the chapter opens on the crisis of enterprise agentic AI — but it is the Chapter 1 folder.)*

## One running example threads everything

The components are never demonstrated in isolation. **Every chapter notebook works a different part of the same investigation:** a DevOps agent paged at 3:47 a.m. for *high latency on `checkout-service`* in a fictional AWS account (`123456789012`).

The tools exist (CloudWatch, X-Ray, logs) but they are disconnected — "there is no graph, there are only strings." Across the chapters the agent builds the vertical graph of the stack, plans an investigation DAG over the horizontal graph, selects and governs the tools it calls, remembers prior incidents, evaluates its remediation, and does it all under a cost budget. Real `boto3` code runs against [`moto`](https://github.com/getmoto/moto)-mocked AWS, so every notebook runs with **zero credentials and zero charges**. Remove the `@mock_aws` decorator and the `AWS_*` env vars to point the identical code at a real account.

## The notebooks

Fourteen Jupyter notebooks. Eight are the pedagogical chapter walkthroughs; six are the original seam-validation spikes that stress the trickiest primitives in isolation.

| Notebook | What it teaches on the running scenario |
|----------|------------------------------------------|
| `notebooks/ch1-defining-agentic-ai.ipynb` | Classify the 3:47 a.m. page: which failure mode is the agent at risk of, is it enterprise-ready, vector vs graph vs hybrid retrieval. |
| `notebooks/ch2-architecture-foundations.ipynb` | **The repo map** (its Section 0 introduces every component). Route the request across the two graphs, split the investigation into harness nodes, map the eight pillars of readiness. |
| `notebooks/ch3-knowledge-representation.ipynb` | Turn the AWS stack (services, dependencies, owners) into a typed graph; route incoming facts into the right graph; enforce authorization per subgraph. |
| `notebooks/ch4-memory.ipynb` | Recall prior `checkout-service` incidents with their time context; update only the changed subgraph; consolidate noisy episodes into durable knowledge. |
| `notebooks/ch5-reasoning-planning.ipynb` | Order hypotheses into an investigation DAG; validate the remediation plan against domain constraints; run parallel probes and reconcile. |
| `notebooks/ch6-tool-orchestration.ipynb` | Select only the tools a latency probe needs from 30+; invoke them through the gateway; policy-check data flow between chained tools. |
| `notebooks/ch7-self-evolution.ipynb` | Capture the whole investigation as an execution graph; score the fix through the eval cascade; attribute a failure to the node that caused it and roll out a targeted fix. |
| `notebooks/ch8-optimization.ipynb` | Route each node to the cheapest model that meets its bar; budget the specialist fleet against KV-cache and latency; scope each persona to its authorized subgraph. |
| `notebooks/spike-*.ipynb` (×6) | Seam-validation spikes: RAG-MCP tool selection, bi-temporal edges, Graphiti incremental update, hierarchical memory, Letta failure modes, and the execution graph. |

## For coding agents: how to leverage the book through this repo

This repo is designed to be driven by a coding agent (Claude Code, Cursor, Gemini CLI, Windsurf, OpenCode) or from a plain shell. The book supplies the *why*; a skill supplies the *decision procedure and the deterministic computation*.

1. **Start at [`AGENTS.md`](./AGENTS.md).** It is the reading contract: the repo's structure, the claims you may cite, and what not to invent.
2. **Find the right skill.** Browse `skills/<chapter-slug>/` by chapter, or grep the one-line `description:` in each `SKILL.md`. Each chapter page under [`docs/`](./docs/README.md) lists its skills with what they do and the exact command.
3. **Load the `SKILL.md` into your context.** It is the operating manual: when to use the primitive, when *not* to, the step-by-step Process, the rationalizations to resist, the red flags, and a Non-Negotiable Verification section. That is the judgment the agent needs.
4. **Call the CLI for the computation.** Every skill self-documents and is deterministic:
   ```bash
   python skills/<chapter>/<skill>/cli.py --help        # prints the SKILL.md description
   python skills/<chapter>/<skill>/cli.py <subcommand>  # each Process step maps to a subcommand/flag
   python skills/<chapter>/<skill>/cli.py benchmark      # the skill's own self-check battery
   ```
   (`mcp-gateway-two-meta-tools` names its self-check `prompt-budget` rather than `benchmark`.)
5. **Compose skills the way the chapters compose.** A latency investigation, for instance, walks `vector-vs-graph-retrieval-selector` → `three-graph-router` → `investigation-dag-planner` → `rag-mcp-tool-selection` → `four-layer-eval-cascade` → `model-routing-selector`, i.e. down the two-graphs-and-a-harness spine.
6. **Run the matching notebook** to see the primitive exercised end-to-end against `moto`-mocked AWS before you wire it into your own system.

The SKILL.md is the agent-facing contract; the CLI is the engine. Nothing about a skill depends on a network call, so an agent can reason about it, run it, and read a stable, testable result.

## The technical stack

Deliberately small, so a skill runs anywhere and an agent can trust it.

| Layer | Choice | Why |
|-------|--------|-----|
| **Skill logic** (`lib.py`) | Pure Python 3.10+ standard library (`dataclasses`, `argparse`, `json`, `difflib`, …). **Zero pip installs to run a skill's logic.** | Portability and no dependency drift. Production swaps (a real embedding model, a real graph DB) are marked as `TODO` at the seam, not baked in. |
| **Skill interface** (`cli.py`) | `argparse` CLI. `--help` prints the SKILL.md description; every Process step maps to a subcommand or flag; a `benchmark` subcommand is the skill's self-check gate. | An agent (or a human, or CI) invokes the same deterministic surface. Self-documenting by construction. |
| **Notebooks** | Jupyter + `boto3` (real AWS SDK call shapes) + `moto` `@mock_aws` (in-memory AWS). | Learn against realistic AWS surfaces with **zero credentials and zero cost**. Swap the decorator to deploy the unchanged code. |
| **Optional LLM cell** | `anthropic` SDK, gated on `ANTHROPIC_API_KEY`. | Notebooks skip the cell gracefully when the key is absent, so the whole notebook still runs offline. |
| **Multi-harness** | `SKILL.md` (agent-facing) + `cli.py` (shell-facing). | The same primitive works in Claude Code / Cursor / Gemini CLI / Windsurf / OpenCode and from cron / CI / scripts. |

Everything the notebooks need is in `requirements.txt` (`anthropic`, `boto3`, `moto[...]`, `jupyter`, `ipykernel`). Running a skill's `cli.py` needs none of it.

## Quickstart

```bash
git clone https://github.com/AnthonyAlcaraz/agentic-graph-rag-skills.git
cd agentic-graph-rag-skills
pip install -r requirements.txt

# A skill self-documents and self-checks — no credentials needed
python skills/tool-orchestration/rag-mcp-tool-selection/cli.py --help
python skills/tool-orchestration/rag-mcp-tool-selection/cli.py benchmark

# Walk the running DevOps investigation for a chapter
jupyter notebook notebooks/ch2-architecture-foundations.ipynb
```

For the optional Anthropic-API cell, set `ANTHROPIC_API_KEY` in your environment; the notebook skips it gracefully if absent. To run any notebook against your own AWS account, remove the `@mock_aws` decorator and the `AWS_*` env vars — the `boto3` code is unchanged.

## How a skill is structured

Each `skills/<chapter>/<skill>/` folder contains:

- **`SKILL.md`** — 7-section anatomy (frontmatter / Overview / When to Use / When NOT to Use / Process / Rationalizations / Red Flags / Non-Negotiable Verification) plus a Security Posture section and a Source Attribution line back to the chapter.
- **`lib.py`** — the pure-Python implementation; production swaps flagged as `TODO` at the seam.
- **`cli.py`** — the `argparse` CLI; `--help` prints the SKILL.md description; every Process step has a subcommand or flag; `benchmark` runs the self-check.
- Asset files (JSON / YAML / sample data) as needed.

Start at [`docs/README.md`](./docs/README.md) for the full architecture map and one page per chapter.

## License

MIT. See `LICENSE`.

## Attribution

Distilled from [*Agentic GraphRAG*](https://www.oreilly.com/library/view/agentic-graphrag/9798341623163/) (O'Reilly, by Anthony Alcaraz and Sam Julien). Each skill cites its source chapter in `SKILL.md` frontmatter. The skills are operational tooling; the book carries the architectural IP.

## Contributing & issues

Found a problem, or want to add a skill? Read [`CONTRIBUTING.md`](./CONTRIBUTING.md) and open a [GitHub issue](https://github.com/AnthonyAlcaraz/agentic-graph-rag-skills/issues). New skills mirror the structure of `skills/tool-orchestration/rag-mcp-tool-selection/` and must pass `python cli.py --help` + a `benchmark` battery; CI enforces both on every push with zero pip installs.
