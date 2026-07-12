# Chapter 5 — Reasoning & Planning

- **Skills folder:** `skills/reasoning-planning/` (6 skills)
- **Notebook:** `notebooks/ch5-reasoning-planning.ipynb`
- **Prev:** [Chapter 4](./04-memory.md) &nbsp;|&nbsp; **Next:** [Chapter 6](./06-tool-orchestration.md)

## Role in the architecture

Plans over the *horizontal* workflow graph. Builds the investigation DAG from hypotheses, selects pipeline architecture, routes loop-vs-pipeline for bounded self-correction, validates plans against constraints, and merges parallel branches.

## In the running DevOps investigation

Hypotheses for the latency spike are ordered into an investigation DAG; the remediation plan is validated against domain constraints before execution; independent probes run in parallel and reconcile.

## Skills

| Skill | What it does | CLI |
|-------|--------------|-----|
| `constraint-guided-plan-validator` | Validate a generated plan against extracted domain constraints AND the agent's capability model before execution (Ch5 Constraint-guided planning, Example 5-14, plus the DevOps hypothesis-formation capability filter). | `python skills/reasoning-planning/constraint-guided-plan-validator/cli.py --help` |
| `investigation-dag-planner` | Dynamic-DAG construction for a planning node (Ch5 Example 5-15 + the DevOps "Constructing the Investigation DAG" section). | `python skills/reasoning-planning/investigation-dag-planner/cli.py --help` |
| `loop-pipeline-router` | The conditional-edge routing that turns a validate node into a bounded self-correcting loop (Ch5 Loop Pipeline + Error-handling strategies, Examples 5-6/5-9). | `python skills/reasoning-planning/loop-pipeline-router/cli.py --help` |
| `parallel-reconcile-merge` | Controlled-parallelism window for a tree pipeline (Ch5 Tree Pipeline + "The architecture of controlled parallelism" + state reducers, Examples 5-7/5-8/5-16). | `python skills/reasoning-planning/parallel-reconcile-merge/cli.py --help` |
| `pipeline-architecture-selector` | Treat pipeline-architecture choice as a routing decision inside a meta-pipeline (Ch5 Hybrid Architectures, Examples 5-10/5-11). | `python skills/reasoning-planning/pipeline-architecture-selector/cli.py --help` |
| `structured-output-contract-designer` | Design the OUTPUT CONTRACT for a graph-agent node's seam, per Ch5 "Structured Generation: The Keystone of Reliable Communication" (Outlines). | `python skills/reasoning-planning/structured-output-contract-designer/cli.py --help` |

## Run it

```bash
# every skill self-documents
python skills/reasoning-planning/constraint-guided-plan-validator/cli.py --help

# the chapter walkthrough against moto-mocked AWS
jupyter notebook notebooks/ch5-reasoning-planning.ipynb
```
