# Chapter 1 — Defining Agentic AI

- **Skills folder:** `skills/crisis/` (5 skills)
- **Notebook:** `notebooks/ch1-defining-agentic-ai.ipynb`
- **Prev:** — &nbsp;|&nbsp; **Next:** [Chapter 2](./02-architecture-foundations.md)

## Role in the architecture

Names the failure modes that motivate the whole stack. Before any architecture, Chapter 1 establishes *why* naive vector RAG collapses in the enterprise and *what* an agent actually is (a spectrum, not a binary).

## In the running DevOps investigation

The 3:47 a.m. `checkout-service` latency page is classified: which failure mode is the agent at risk of (action blindness, memory loss), is it enterprise-ready, and should this incident query use vector, graph, or hybrid retrieval.

## Skills

| Skill | What it does | CLI |
|-------|--------------|-----|
| `agent-constraint-triangle-scorer` | Score an agent configuration against Ch1's Agent Constraint Triangle — the three interconnected constraints (complexity management, tool orchestration, context utilization) that make agent design an inherently difficult operational problem. | `python skills/crisis/agent-constraint-triangle-scorer/cli.py --help` |
| `context-failure-classifier` | Classify an observed agent symptom into Ch1's context-failure taxonomy. | `python skills/crisis/context-failure-classifier/cli.py --help` |
| `enterprise-readiness-scorer` | Score a proposed or deployed enterprise agent against the architectural requirements Ch1 argues are non-negotiable: absence of the five fatal flaws of naive vector RAG (context amnesia / relationship blindness / temporal ignorance / reasoning paralysis / tool chaos), calibration of the three agency dimensions (autonomy / action / authority), presence of the four emergent capabilities, and the decision-trace test that separates a real context graph from a relabeled search index. | `python skills/crisis/enterprise-readiness-scorer/cli.py --help` |
| `vector-vs-graph-retrieval-selector` | Recommend VECTOR / GRAPH / HYBRID retrieval for a query workload, grounded in Ch1's BenchmarkQED evidence for where vector RAG succeeds and where it collapses. | `python skills/crisis/vector-vs-graph-retrieval-selector/cli.py --help` |
| `workflow-agent-spectrum-classifier` | Place an AI system on Ch1's continuous workflow-agent spectrum instead of the false binary "is it an agent or not". | `python skills/crisis/workflow-agent-spectrum-classifier/cli.py --help` |

## Run it

```bash
# every skill self-documents
python skills/crisis/agent-constraint-triangle-scorer/cli.py --help

# the chapter walkthrough against moto-mocked AWS
jupyter notebook notebooks/ch1-defining-agentic-ai.ipynb
```
