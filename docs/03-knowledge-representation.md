# Chapter 3 — Knowledge Representation

- **Skills folder:** `skills/knowledge-representation/` (8 skills)
- **Notebook:** `notebooks/ch3-knowledge-representation.ipynb`
- **Prev:** [Chapter 2](./02-architecture-foundations.md) &nbsp;|&nbsp; **Next:** [Chapter 4](./04-memory.md)

## Role in the architecture

Fills the *vertical* knowledge graph. Chooses the graph model (LPG / RDF / hypergraph) by reasoning requirement, routes facts into the three-graph architecture (domain / lexical / episodic), selects schema patterns, and gates capability authorization.

## In the running DevOps investigation

The AWS infrastructure (services, dependencies, owners) becomes a typed graph; incoming telemetry facts route into the right graph; the agent's authorization to touch each subgraph is enforced.

## Skills

| Skill | What it does | CLI |
|-------|--------------|-----|
| `capability-authorization-gate` | Runtime authorization gate built on the Ch3 Capability Model Pattern — a self-aware agent represents its own capabilities, required resources/grants, authorization level, and quantitative limits as queryable structure, then checks at PLANNING time whether it may perform an action BEFORE attempting it. | `python skills/knowledge-representation/capability-authorization-gate/cli.py --help` |
| `entity-resolution-strategy-selector` | Choose HOW to decide when two records are the same real-world entity — EVIDENCE-BASED resolution (deterministic feature-by-feature scoring with explainable evidence and culturally-robust rules) vs GENERALIZATION-BASED AI (LLM statistical similarity, nondeterministic, post-hoc rationalization) — per Ch3 "Entity Resolution: The Foundation of Agent Knowledge". | `python skills/knowledge-representation/entity-resolution-strategy-selector/cli.py --help` |
| `graph-model-selector` | Select a graph data model — labeled property graph (LPG) vs RDF vs hypergraph — by scoring REASONING REQUIREMENTS against five implementation features (formal reasoning, n-ary relations, performance, tool ecosystem, constraint expressiveness), per Ch3 "Evaluating Graph Models". | `python skills/knowledge-representation/graph-model-selector/cli.py --help` |
| `homoiconic-meta-schema` | Homoiconic knowledge representation (Ch3) — code and data share the same representation so an agent can inspect and modify its own knowledge structures with the same machinery it uses for regular data. | `python skills/knowledge-representation/homoiconic-meta-schema/cli.py --help` |
| `kg-extraction-approach-selector` | Select a knowledge-graph EXTRACTION approach for a given source — structured database integration vs LLM-based triple extraction vs iText2KG (incremental) vs RAKG (document-level) — by scoring a SOURCE PROFILE against five features (handles unstructured text, incremental-friendly, document-level context, determinism, setup cost), per Ch3 "Extraction Approaches for Heterogeneous Sources". | `python skills/knowledge-representation/kg-extraction-approach-selector/cli.py --help` |
| `knowledge-organization-classifier` | Classify an organizational vocabulary onto the Ch3 knowledge-organization spectrum — pick list -> taxonomy -> thesaurus -> ontology — by the structural features the spec actually exhibits, walking bottom-up so a partial ontology does NOT over-claim. | `python skills/knowledge-representation/knowledge-organization-classifier/cli.py --help` |
| `schema-pattern-selector` | Select and validate the four agent schema design patterns from Ch3 — Event-Centric (temporal reasoning), Contextual-Boundary (scope/validity boundaries), Multi-Perspective (contradictory viewpoints with attribution and confidence), and Capability-Model (agent self-awareness of authority limits). | `python skills/knowledge-representation/schema-pattern-selector/cli.py --help` |
| `three-graph-router` | Route an incoming record/fact into the correct graph of the Three-Graph Architecture (Ch3) — DOMAIN (trusted, entity-resolved single source of truth), LEXICAL (verbatim source text with provenance, the "retrieval" in RAG), or SUBJECT (LLM-extracted artifacts kept SEPARATE from domain until entity resolution links them). | `python skills/knowledge-representation/three-graph-router/cli.py --help` |

## Run it

```bash
# every skill self-documents
python skills/knowledge-representation/capability-authorization-gate/cli.py --help

# the chapter walkthrough against moto-mocked AWS
jupyter notebook notebooks/ch3-knowledge-representation.ipynb
```
