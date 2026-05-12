# PLAN.md — agentic-graph-rag-skills

Companion repo for *Agentic Graph RAG* (O'Reilly). Practical, multi-harness skills + AWS-serverless DevOps notebooks distilled from chapters Ch3-Ch7 of the book.

## Scope

| Decision | Locked |
|----------|--------|
| Book chapters covered | Ch3, Ch4, Ch5, Ch6, Ch7 (Knowledge Representation, Memory, Reasoning & Planning, Tool Orchestration, Self-Evolution & Evaluation). Ch1, Ch2 excluded. |
| Chapter access | `~/scripts/google-api.js docs text <docId>` against Google Drive folder `1WjuZ9DSC-A3yNnOVJ7zMz7g6P4xdr5qY` |
| Skill format | Osmani 7-section SKILL.md + hand-rolled Python CLI per skill (CLI-Anything wrapping is a follow-up once the plugin is installed) |
| Harness target | Multi-harness — SKILL.md works in Claude Code, Cursor, Gemini CLI, Windsurf, OpenCode; CLI works from cron / CI / scripts |
| Skill granularity | As many as relevant; hierarchical namespacing `skills/<chapter-slug>/<skill-slug>/` keeps each subfolder under the Reganti SkillsBench 80-flat-skill retrieval-collapse threshold |
| Devops use case | Book's running DevOps-agent latency-investigation example (introduced Ch5/6) running against a **fictional AWS account `123456789012`** — real boto3 code, real AWS service shapes, mocked via `moto` so notebooks run with zero AWS credentials |
| Repo name + license | `agentic-graph-rag-skills` / MIT / `AnthonyAlcaraz` owner / public |
| LLM API | `ANTHROPIC_API_KEY` from end-user environment, never bundled in repo |

## Vertical-slice ordering (Pocock principle, applied at this plan-phase)

Tasks ordered high-risk-first. Each task names the assumption it validates.

### Spike A — chapter→skill→CLI→notebook seam (highest risk, smallest scope)

**Goal:** Validate one concrete chapter primitive can round-trip through a SKILL.md, hand-rolled Python CLI, and a Jupyter notebook that exercises the skill against a fictional AWS DevOps scenario. **Assumption:** the seam works end-to-end without surprises.

**Primitive chosen:** RAG-MCP tool selection (Ch5/6 — Tool Orchestration). Concrete, falsifiable, benchmark-anchored in the book (50-70% prompt token reduction). Maps cleanly onto the DevOps latency-investigation use case (filter ~30 AWS service tools down to the 3-5 relevant for a latency query).

**Spike A artifacts:**
- `skills/tool-orchestration/rag-mcp-tool-selection/SKILL.md` (Osmani Generator pattern, Ghosh Primitive layer)
- `skills/tool-orchestration/rag-mcp-tool-selection/lib.py` (pure-Python word-overlap retrieval; production-encoder swap documented as TODO)
- `skills/tool-orchestration/rag-mcp-tool-selection/cli.py` (argparse CLI)
- `skills/tool-orchestration/rag-mcp-tool-selection/sample-aws-tools.json` (~30 real AWS service tools with boto3-derived descriptions)
- `notebooks/spike-a-rag-mcp-tool-selection.ipynb` (DevOps latency scenario with `moto` mocks against fictional account `123456789012`)

**Verification gates:**
- [ ] CLI `--help` exits 0 and prints SKILL.md description verbatim
- [ ] CLI can return top-K tools for a query against `sample-aws-tools.json`
- [ ] Notebook runs top-to-bottom without errors against `moto`-mocked AWS
- [ ] Notebook prints measurable token reduction (baseline-all-tools vs RAG-filtered-tools) per the book's claim
- [ ] At least one boto3 call (CloudWatch Logs Insights or CloudWatch Metrics) executes against mocked AWS and returns shaped data

If any gate fails: revise the spec before broader chapter conversion. The skill of writing a chapter→SKILL.md round-trip is the broader pattern; if it doesn't work for one primitive, it won't work for 30+.

### Spike A.5 — CLI-Anything wrap (after Spike A passes)

Install `cli-anything` plugin via `/plugin marketplace add HKUDS/CLI-Anything` then regenerate the spike's CLI through `/cli-anything skills/tool-orchestration/rag-mcp-tool-selection/`. Verify the auto-generated CLI matches the hand-rolled one's behavior. This is the multi-harness payoff — every subsequent skill ships with CLI-Anything wrapping by default per CLAUDE.md Skill Creation Protocol.

### Spike B — AWS deployment (after Spike A passes, requires AWS auth refresh)

**Goal:** Deploy the RAG-MCP tool selection logic to an actual AWS Lambda function. **Assumption:** the SAM template + IAM scoping + free-tier deployment works.

Blocked until: `aws sts get-caller-identity` succeeds. Current `[default]` profile credentials return `InvalidClientTokenId` — keys need refresh via IAM console or `aws sso login`.

### Phase 1 — Chapter conversion (after Spike A passes)

Convert one chapter at a time, ordered by content density. For each chapter:
1. Pull text via `~/scripts/google-api.js docs text <docId>` to gitignored `chapter-content/`
2. Identify 5-10 primitives suitable for skill extraction (architecturally distinct, falsifiable, code-able)
3. Generate one skill per primitive following the Spike A template
4. Write one notebook per chapter exercising the chapter's primitives against the DevOps running example

Chapter order: **Ch5 → Ch4 → Ch6 → Ch7 → Ch3**. Rationale: Ch5/6 has the running DevOps example threaded through it (lowest unknown-unknowns); Ch4 (Memory) is dense but standalone; Ch7 (Self-Evolution) depends on Ch4-Ch6; Ch3 (Knowledge Representation) is foundational but graph-heavy and benefits from having the other chapters' primitives available first.

### Phase 2 — CDLC notebook flight (after Phase 1 passes)

Per Debois CDLC 6-phase loop (Generate / Test / Distribute / Observe / Adapt / Regenerate — Ch5/6 canonical), one notebook per phase, each exercising the relevant chapter skills:
- `01-generate.ipynb` — agent generates a DevOps response
- `02-test.ipynb` — eval gate
- `03-distribute.ipynb` — skill packaging + registry update
- `04-observe.ipynb` — CloudWatch Logs Insights query
- `05-adapt.ipynb` — feedback ingestion
- `06-regenerate.ipynb` — improved response

All notebooks run against fictional account `123456789012` with `moto` mocks. End-users can swap to their real AWS account by removing the `@mock_aws` decorator.

### Phase 3 — Repository polish (after Phase 2 passes)

- Top-level `README.md` with quickstart, chapter map, skill index, license, attribution to the O'Reilly book
- CI: `.github/workflows/skill-lint.yml` (validate SKILL.md frontmatter + CLI `--help` smoke test for every skill)
- `LICENSE` (MIT)
- `requirements.txt` pinned versions
- `gh repo create AnthonyAlcaraz/agentic-graph-rag-skills --public --source=.`
- `git push -u origin main`

## Out of scope

- Real AWS deployment of every notebook (Spike B handles one; the rest stay mock-only by design — readers run them against their own accounts)
- Ch1 + Ch2 content
- The Z9-Chapter-Revisions.md files in the OneDrive vault (those are revision artifacts, not chapter prose)
- Any rewrite of the book itself
- O'Reilly publishing pipeline integration (this is a companion, not a co-publication)

## Reverse-out path

This is a new directory at `~/projects/agentic-graph-rag-skills/`. Reverse-out is `rm -rf ~/projects/agentic-graph-rag-skills/`. No changes to existing repos or system state. The `~/scripts/google-api.js` token at `~/.credentials/token.json` was refreshed today; that survives reverse-out and remains useful for `/book-revision` work.
