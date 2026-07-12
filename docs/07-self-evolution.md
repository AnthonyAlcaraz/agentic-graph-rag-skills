# Chapter 7 — Self-Evolution & Evaluation

- **Skills folder:** `skills/self-evolution/` (7 skills)
- **Notebook:** `notebooks/ch7-self-evolution.ipynb`
- **Prev:** [Chapter 6](./06-tool-orchestration.md) &nbsp;|&nbsp; **Next:** [Chapter 8](./08-optimization.md)

## Role in the architecture

Closes the loop. The execution graph records every decision as the agent's autobiography, a four-layer eval cascade stops at the first failing layer, semantic backprop attributes failure to the causal node, and graduated validation gates what reaches production.

## In the running DevOps investigation

The whole investigation is captured as an immutable execution graph; the remediation is scored through the eval cascade; a failure is attributed to the node that caused it and a targeted intervention is chosen and safely rolled out.

## Skills

| Skill | What it does | CLI |
|-------|--------------|-----|
| `evolution-taxonomy-classifier` | Locate a proposed self-evolution in the four-dimensional design space Gao et al. | `python skills/self-evolution/evolution-taxonomy-classifier/cli.py --help` |
| `execution-graph` | Foundational Ch7 primitive: an immutable, queryable graph of every decision / retrieval / tool-call / LLM-call an agent made for a specific query. | `python skills/self-evolution/execution-graph/cli.py --help` |
| `four-layer-eval-cascade` | The Multi-Layered Evaluation Framework as a sequential diagnostic cascade that STOPS at the first failing layer. | `python skills/self-evolution/four-layer-eval-cascade/cli.py --help` |
| `graduated-validation-protocol` | The Ch7 safety envelope for a self-evolving agent: the RPO spine (Recursion, Provenance, Optimization) plus the Graduated Validation Protocol that gates what reaches production. | `python skills/self-evolution/graduated-validation-protocol/cli.py --help` |
| `intervention-selector` | Ch7 self-evolution router: map a diagnostic report to exactly one intervention, deterministically and auditably, not as a per-engineer judgment call. | `python skills/self-evolution/intervention-selector/cli.py --help` |
| `semantic-backprop-attributor` | Ch7 self-evolution primitive: attribute a failure to the node that actually caused it, then generate NEIGHBOR-AWARE textual feedback that flows backward through the execution graph from the point of failure. | `python skills/self-evolution/semantic-backprop-attributor/cli.py --help` |
| `xskill-self-improving-object` | Turn execution traces into knowledge that improves without retraining. | `python skills/self-evolution/xskill-self-improving-object/cli.py --help` |

## Run it

```bash
# every skill self-documents
python skills/self-evolution/evolution-taxonomy-classifier/cli.py --help

# the chapter walkthrough against moto-mocked AWS
jupyter notebook notebooks/ch7-self-evolution.ipynb
```
