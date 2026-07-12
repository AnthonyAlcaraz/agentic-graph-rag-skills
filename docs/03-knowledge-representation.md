# Chapter 3 — Knowledge Representation

- **Skills folder:** `skills/knowledge-representation/` (6 skills)
- **Notebook:** `notebooks/ch3-knowledge-representation.ipynb`
- **Prev:** [Chapter 2](./02-architecture-foundations.md) &nbsp;|&nbsp; **Next:** [Chapter 4](./04-memory.md)

## Role in the architecture

Fills the *vertical* knowledge graph. Chooses the graph model (LPG / RDF / hypergraph) by reasoning requirement, routes facts into the three-graph architecture (domain / lexical / episodic), selects schema patterns, and gates capability authorization.

## In the running DevOps investigation

The AWS infrastructure (services, dependencies, owners) becomes a typed graph; incoming telemetry facts route into the right graph; the agent's authorization to touch each subgraph is enforced.

## Skills

| Skill | What it does | CLI |
|-------|--------------|-----|
| `capability-authorization-gate` | Runtime authorization gate built on the Ch3 Capability Model Pattern — | `python skills/knowledge-representation/capability-authorization-gate/cli.py --help` |
| `graph-model-selector` | Select a graph data model — | `python skills/knowledge-representation/graph-model-selector/cli.py --help` |
| `homoiconic-meta-schema` | Homoiconic knowledge representation (Ch3) — | `python skills/knowledge-representation/homoiconic-meta-schema/cli.py --help` |
| `knowledge-organization-classifier` | Classify an organizational vocabulary onto the Ch3 knowledge-organization spectrum — | `python skills/knowledge-representation/knowledge-organization-classifier/cli.py --help` |
| `schema-pattern-selector` | Select and validate the four agent schema design patterns from Ch3 — | `python skills/knowledge-representation/schema-pattern-selector/cli.py --help` |
| `three-graph-router` | Route an incoming record/fact into the correct graph of the Three-Graph Architecture (Ch3) — | `python skills/knowledge-representation/three-graph-router/cli.py --help` |

## Run it

```bash
# every skill self-documents
python skills/knowledge-representation/capability-authorization-gate/cli.py --help

# the chapter walkthrough against moto-mocked AWS
jupyter notebook notebooks/ch3-knowledge-representation.ipynb
```
