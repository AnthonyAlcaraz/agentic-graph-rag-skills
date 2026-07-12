# Chapter 8 — Optimization

- **Skills folder:** `skills/optimization/` (5 skills)
- **Notebook:** `notebooks/ch8-optimization.ipynb`
- **Prev:** [Chapter 7](./07-self-evolution.md) &nbsp;|&nbsp; **Next:** —

## Role in the architecture

Makes it affordable. Routes each node to the cheapest sufficient model, scores cost-per-successful-completion, budgets KV-cache-bound concurrency and latency, scopes subgraph access per persona, and migrates schema without breaking consumers.

## In the running DevOps investigation

Each investigation node is routed to the cheapest model that meets its quality bar; the specialist fleet is budgeted against KV-cache and latency limits; each persona sees only its authorized subgraph.

## Skills

| Skill | What it does | CLI |
|-------|--------------|-----|
| `cost-performance-scorer` | Score a multi-model routing policy on cost versus quality using the two metrics that actually decide selective intelligence: cost per successful completion (not cost per token) and a per-node quality parity threshold wit | `python skills/optimization/cost-performance-scorer/cli.py --help` |
| `kv-cache-latency-budgeter` | Budget a specialist model fleet against the two production bottlenecks: KV-cache-bound concurrency and end-to-end latency. | `python skills/optimization/kv-cache-latency-budgeter/cli.py --help` |
| `model-routing-selector` | Match model capability to task complexity across a horizontal workflow graph. | `python skills/optimization/model-routing-selector/cli.py --help` |
| `schema-evolution-migrator` | Keep a production knowledge graph healthy across schema evolution, node/edge lifecycle, incremental updates, and coordinated deployment. | `python skills/optimization/schema-evolution-migrator/cli.py --help` |
| `subgraph-access-control` | Scope what each agent persona can see in a knowledge graph. | `python skills/optimization/subgraph-access-control/cli.py --help` |

## Run it

```bash
# every skill self-documents
python skills/optimization/cost-performance-scorer/cli.py --help

# the chapter walkthrough against moto-mocked AWS
jupyter notebook notebooks/ch8-optimization.ipynb
```
