# Contributing

Thanks for wanting to improve the companion repo for [*Agentic GraphRAG*](https://www.oreilly.com/library/view/agentic-graphrag/9798341623163/) (O'Reilly, by Anthony Alcaraz and Sam Julien).

## Reporting problems

Open a [GitHub issue](https://github.com/AnthonyAlcaraz/agentic-graph-rag-skills/issues). The most useful reports include: the skill or notebook, the exact command you ran, and what you expected versus what happened. Errata about the *book text* go through the O'Reilly errata page, not this repo.

## Adding or changing a skill

Every skill is one architectural primitive from one book chapter, packaged as a self-contained folder:

```
skills/<chapter-slug>/<skill-slug>/
├── SKILL.md   # the agent-facing operating manual
├── lib.py     # pure Python 3.10+ standard library — no pip installs
├── cli.py     # argparse CLI over lib.py
└── *.json     # sample data as needed
```

Mirror the structure of `skills/tool-orchestration/rag-mcp-tool-selection/` (the reference skill). A PR must satisfy all of:

1. **SKILL.md** follows the 7-section anatomy used across the repo: frontmatter (`name`, `description`, `chapter-source`), Overview, When to Use, When NOT to Use, Process, Rationalizations, Red Flags, Non-Negotiable Verification — plus a Security Posture section and a Source Attribution line back to the chapter.
2. **`lib.py` is standard-library only.** Production integrations (embedding models, LLM calls, real graph DBs) are marked as `TODO` at the seam, never imported.
3. **`python cli.py --help` exits 0** and prints the SKILL.md description.
4. **`python cli.py benchmark` passes** — a self-check battery asserting the skill's documented behavior, including at least one negative case.
5. **A notebook cell exercises the skill** against the running DevOps scenario (`moto`-mocked AWS, fictional account `123456789012`) if the skill belongs in a chapter walkthrough.

CI (`.github/workflows/skill-lint.yml`) enforces 2–4 for every skill on every push — deliberately with **zero pip installs**, which is what keeps claim 2 honest.

## Style

- Keep CLI output plain ASCII (it must render on a cp1252 Windows console).
- No network calls anywhere in a skill: an agent must be able to reason about it, run it, and get a deterministic result.
- The book carries the theory. A skill's SKILL.md distills the decision procedure; it never reproduces book prose.
