---
name: skill-quality-evaluator
description: |
  Score a skill against SkillNet's five quality dimensions (safety,
  completeness, executability, maintainability, cost_awareness), compute a
  safety/executability-weighted composite, and gate skill retrieval so an
  agent pulls the most-relevant skill that ALSO clears a quality threshold.
  Use when a skill library has grown past a few dozen entries and retrieval
  is surfacing low-quality or unsafe skills alongside useful ones. NOT for
  routing (which skill matches this task? — that is rag-mcp-tool-selection),
  NOT for a library under ~20 curated skills (quality is still trivially
  auditable by hand), NOT a substitute for a security scanner (executability
  and safety scores are heuristics that flag review, not proofs).
osmani-pattern: Reviewer
ghosh-layer: Workflow
chapter-source: "Agentic GraphRAG (O'Reilly) Ch6 — Tool Orchestration"
---

# Skill Quality Evaluator

## Overview

RAG and gateways (the two sibling Ch6 skills) solve the routing problem: which
skill matches this task? They do not solve the quality problem: is this skill
worth trusting once matched? Raw skill libraries accumulate junk. As a
repository scales from dozens to hundreds to thousands of skills, retrieval
quality degrades because the agent pulls low-quality or unsafe skills alongside
the useful ones.

The chapter grounds this in two research anchors:

- **SkillsBench (DAIR.AI).** Curated skills improve task performance by 16.2%.
  Self-generated skills — produced by agents without human review — show zero
  improvement over baseline. Quality matters more than quantity, and 2-3
  focused skills per task is the optimal number.
- **SkillNet (2026).** A repository of 200,000+ reusable skills, each rated
  across five quality dimensions. Agents using SkillNet-rated skills achieved
  40% higher average rewards and 30% fewer execution steps across ALFWorld,
  WebShop, and ScienceWorld — held across multiple backbone models, confirming
  quality-rated retrieval is a model-agnostic infrastructure layer.

The five dimensions (Table 6-1) and the composite weighting:

| Dimension | Weight | Maps to |
|-----------|--------|---------|
| safety | 2.0 | security scanning |
| completeness | 1.0 | dependency checking |
| executability | 2.0 | hallucinated-tool-call risk |
| maintainability | 1.0 | composability |
| cost_awareness | 1.0 | token economics (Ch8) |

Composite = weighted mean with safety and executability at double weight, so a
skill that hallucinates tool calls (low executability) or runs unconstrained
shell commands (low safety) ranks low regardless of how well it documents.

## When to Use

- A skill library has grown past ~20 entries and mixed provenance (vendor,
  team-authored, agent-generated)
- Retrieval is surfacing plausible-but-junk skills alongside good ones
- You need a deployment knob (`min_quality`) that encodes organizational risk
  appetite (research 0.4 → production healthcare 0.8+)
- You are integrating quality as a second ranking signal on top of relevance

Phrases that invoke this skill: "rate this skill", "quality gate", "SkillNet",
"is this skill safe to use", "why did the agent pick a bad skill".

## When NOT to Use

- **Routing / matching.** Which skill fits the task is `rag-mcp-tool-selection`
  or the gateway. This skill assumes a matched candidate set and filters it.
- **Libraries under ~20 curated skills.** The chapter's tip: start with a
  curated, quality-gated set (hundreds, not thousands). Below that, hand audit.
- **As a security scanner.** `safety` and `executability` are heuristic scores
  that flag a skill for review; they are not a substitute for `agent-shield` /
  SkillSpector static analysis before install.
- **As a self-generation approver.** SkillsBench shows self-generated skills
  score zero improvement; a passing composite does not license auto-install of
  agent-authored skills without human curation.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Skills catalog JSON (each skill carries eval_safety/completeness/executability/maintainability/cost_awareness) | `lib.load_catalog(path)` | List of skill dicts | `len(catalog) > 0`; each skill has all five `eval_*` keys in [0,1] |
| 2 | One skill dict | `lib.SkillQuality.from_skill(skill).composite` | Composite float in [0,1] | Safety+executability weighted 2x; recompute by hand for one skill to confirm /7 mean |
| 3 | Task description + catalog | `lib.retrieve_quality_gated(task, catalog, min_quality=0.6, top_k=3)` | Top-K skills passing the gate, ranked by relevance*quality | Hard gate: `eval_safety>0 AND eval_executability>0`; soft gate: `composite >= min_quality` |
| 4 | Same, varying `min_quality` | `lib.retrieve_quality_gated(..., min_quality=0.8)` | Smaller/empty result | Raising the threshold monotonically shrinks the result set |
| 5 | Catalog + a battery of task queries | `lib.monitor_gaps(catalog, queries, min_quality)` | Counts of `no_relevant_skill` vs `low_quality_filtered` events | Interpret: many no-relevant = repository too small; many low-quality-filtered = gate too permissive OR catalog quality poor |
| 6 | Selected skill | (your agent runtime) loads the SKILL.md and executes | Task result | If the top skill still misbehaves, its `eval_*` ratings are stale — re-rate |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|---------------------|
| "More skills always help — just retrieve top-K by relevance." | SkillsBench: self-generated (unrated) skills give zero improvement, and 2-3 focused skills per task is optimal. Relevance without a quality gate re-admits the junk that degrades retrieval at scale. |
| "Weight all five dimensions equally — it's simpler." | The chapter weights safety and executability 2x deliberately: a skill that runs unconstrained shell commands or hallucinates tool calls is dangerous regardless of maintainability. Equal weighting lets a well-documented unsafe skill outrank a plain safe one. |
| "Rank by quality alone — always pick the highest-rated skill." | The chapter ranks by `relevance * quality` multiplicatively. Pure quality ranking returns the best skill for the wrong task. Pure relevance returns the junk. The product is the point. |
| "Set min_quality once globally." | The threshold is a per-deployment risk decision: 0.4 for research to cast a wide net, 0.8+ for production healthcare. One global value ignores that risk appetite differs by system. |
| "A high composite means the skill is safe to auto-install." | Composite is a retrieval-ranking signal, not an install gate. Self-generated skills need human curation (SkillsBench) and static scanning (agent-shield/SkillSpector) before install regardless of score. |

## Red Flags

- **Every skill scores above min_quality.** The ratings are inflated or the gate
  is too low; the monitor will show near-zero `low_quality_filtered` events even
  on a junk-laden catalog.
- **Safety or executability is 0 but the skill still ranks.** The hard gate
  (`eval_safety>0 AND eval_executability>0`) is being bypassed — a zero on either
  dimension must exclude the skill entirely, not merely lower it.
- **Raising min_quality does not shrink results.** The soft gate is not wired;
  the threshold knob is inert.
- **High `no_relevant_skill` AND high `low_quality_filtered` together.** The
  repository is both too small and too junky — grow the curated set, do not just
  lower the gate.
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch; the multi-harness
  invariant is broken.

## Non-Negotiable Verification

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirm the gate admits high-quality skills and rejects the seeded
   low-quality ones across the task battery, and that raising `--min-quality`
   monotonically shrinks the admitted set.

2. **Hand-check one composite.**
   ```
   python cli.py rate safe-readonly-sql-query
   ```
   Recompute `(safety*2 + completeness + executability*2 + maintainability +
   cost_awareness) / 7` by hand and confirm it matches.

3. **Prove the hard gate.**
   ```
   python cli.py retrieve "run a shell command to clean up disk" --json
   ```
   Confirm the seeded `unsafe-shell-runner` skill (eval_safety = 0) never
   appears, even when it is the most textually relevant.

4. **JSON round-trips.**
   ```
   python cli.py retrieve "..." --json | python -c "import json,sys; json.load(sys.stdin)"
   ```

## Security Posture

- **Prompt injection.** Skill descriptions and `synthetic_queries` are used for
  relevance matching; treat them as untrusted if the catalog ingests
  community-contributed skills. A malicious skill could inflate its own `eval_*`
  ratings — ratings must come from an independent evaluator, not self-reported by
  the skill author. The `# TODO(production):` seam in `lib.score_relevance` and
  the rating-provenance note in `load_catalog` mark where to enforce this.
- **Data exfiltration.** No network calls in `lib.py`; catalog is read from an
  explicit path.
- **Privilege escalation.** The `safety` dimension is the flag for skills that
  execute shell / write files / hold broad credentials. A zero on `safety` hard-
  excludes; do not soften that gate to admit a convenient-but-unsafe skill.

## Composition

- **Composes after** `rag-mcp-tool-selection` / `mcp-gateway-two-meta-tools`:
  they return the relevant candidate set; this skill filters that set by quality.
- **Feeds** graph-based retrieval — the composite maps to the Cypher
  `relevance * quality DESC` ordering in the chapter's Example 6-3.
- **Pairs with** `agent-shield` / SkillSpector at the install boundary (this
  skill gates retrieval, those gate installation).
- **cost_awareness** links directly to the Ch8 token-economics material.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly), Chapter 6 — Tool Orchestration,
sections "Skills: The Judgment Layer", "Skill quality evaluation", "Integrating
quality ratings into graph-based retrieval", and "Scale and retrieval". Named
references:

- SkillsBench (DAIR.AI) — 16.2% curated-skill improvement; zero for
  self-generated; 2-3 focused skills per task optimal
- SkillNet (2026) — 200,000-skill repository; five-dimensional rating; 40%
  higher rewards / 30% fewer steps across ALFWorld, WebShop, ScienceWorld
- SkillRL — 10-20x token compression per skill; 7B model at 89.9% on ALFWorld
- Anthropic Agent Skills specification — SKILL.md progressive disclosure
