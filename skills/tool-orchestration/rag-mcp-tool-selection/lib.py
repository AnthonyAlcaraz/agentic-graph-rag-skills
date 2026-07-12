"""
RAG-MCP tool selection — three-step retrieval pipeline.

Distilled from Agentic GraphRAG (O'Reilly), Chapter 5/6 — Tool Orchestration.

The standard MCP `tools/list` operation returns every tool the agent has access
to. At enterprise scale (the book cites Block's Goose agent: 12,000 employees,
60+ MCP servers) this consumes the entire context window before the agent has
done any reasoning. The RAG-MCP framework replaces `tools/list` with a semantic
search over tool metadata, returning only the top-k tools whose descriptions
match the user query.

Reported benchmarks from the chapter:
- Prompt tokens reduced 50-70% (avg 2134 -> 1084)
- Selection accuracy 13.62% -> 43.13%
- Response time -60%

This module implements the three-step pipeline (retrieval / validation /
invocation) with a deliberately simple word-overlap retriever so the spike has
zero ML dependencies. A production deployment should swap `score_tool` for a
sentence-transformer or hosted embedding API (Voyage, Cohere, OpenAI ada).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have he in is it its of on or "
    "that the their to was were will with you your this these those what "
    "which who whom whose how can could should would do does did".split()
)


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens with stopwords removed."""
    return {t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in _STOPWORDS}


@dataclass(frozen=True)
class ScoredTool:
    tool: dict
    score: float

    @property
    def name(self) -> str:
        return self.tool["name"]


def load_registry(path: str | Path) -> list[dict]:
    """Load the tool registry JSON. Returns the list of tool dicts."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["tools"]


def _enhanced_text(tool: dict) -> str:
    """
    Toolshed enhanced representation (Ch5/Ch6 — Zhu et al.).
    Concatenate name + description + synthetic queries + key topics into one
    searchable text. Multiple semantic hooks make the tool findable by what
    it does, how it's used, and what problems it solves.
    """
    parts = [
        tool["name"].replace("_", " "),
        tool["description"],
        " ".join(tool.get("synthetic_queries", [])),
        " ".join(tool.get("key_topics", [])),
    ]
    return " ".join(parts)


def score_tool(tool: dict, query_tokens: set[str]) -> float:
    """
    Word-overlap scoring against the enhanced tool representation.

    Production-encoder swap: replace this function with a call to a sentence
    transformer or hosted embedding API. The retrieval contract (returns a
    float score, higher = more relevant) is the seam.
    """
    tool_tokens = _tokenize(_enhanced_text(tool))
    if not tool_tokens or not query_tokens:
        return 0.0
    overlap = query_tokens & tool_tokens
    return len(overlap) / (len(query_tokens) ** 0.5 * len(tool_tokens) ** 0.5)


def retrieve(query: str, registry: Iterable[dict], top_k: int = 5) -> list[ScoredTool]:
    """
    Step 1 — Retrieval. Score every tool against the query and return top-k.

    The chapter notes that with 10 tools the model achieves near-perfect
    selection; with 1000 tools selection accuracy plummets below 40%. Top-k
    in production is typically 3-5; the SkillsBench finding cited in Ch5
    says 2-3 focused skills per task is the optimal number.
    """
    q_tokens = _tokenize(query)
    scored = [ScoredTool(tool=t, score=score_tool(t, q_tokens)) for t in registry]
    scored.sort(key=lambda s: s.score, reverse=True)
    return [s for s in scored[:top_k] if s.score > 0]


def validate(scored_tools: list[ScoredTool], query: str) -> list[ScoredTool]:
    """
    Step 2 — Validation. Optionally drop tools whose name does not share any
    domain token with the query. This catches the obvious description-keyword
    matches that point at the wrong tool category (Ch5: 'A tool that seems
    relevant based on its description but actually serves a different
    purpose').

    The full validation step described in the chapter generates synthetic
    example queries via an LLM and checks compatibility. For the spike we
    use the cheaper domain-token sanity check.
    """
    q_tokens = _tokenize(query)
    out = []
    for st in scored_tools:
        name_tokens = _tokenize(st.tool["name"].replace("_", " "))
        topic_tokens = _tokenize(" ".join(st.tool.get("key_topics", [])))
        if (name_tokens | topic_tokens) & q_tokens:
            out.append(st)
        elif st.score > 0.3:
            out.append(st)
    return out


def invoke_prompt(
    selected: list[ScoredTool], query: str
) -> str:
    """
    Step 3 — Invocation. Format the top-k tool descriptions for injection
    into the LLM prompt. Only the selected tool descriptions go in; the
    other ~25 tools in the registry never enter the context window.
    """
    lines = [f"You are a DevOps agent. The user's query: {query!r}\n"]
    lines.append("You may use the following tools (selected by RAG-MCP from a larger registry):\n")
    for st in selected:
        lines.append(f"- {st.tool['name']}: {st.tool['description']}")
        params = st.tool.get("parameters", {})
        if params:
            param_summary = ", ".join(f"{k}={v}" for k, v in params.items())
            lines.append(f"  parameters: {param_summary}")
    lines.append(
        "\nDecide which tool to call, with what parameters, and explain your reasoning."
    )
    return "\n".join(lines)


def baseline_prompt(registry: Iterable[dict], query: str) -> str:
    """
    Baseline — what the agent would see WITHOUT RAG-MCP: every tool in the
    registry dumped into the prompt. Useful for measuring the token-reduction
    benchmark the chapter claims.
    """
    tools = list(registry)
    lines = [f"You are a DevOps agent. The user's query: {query!r}\n"]
    lines.append("You may use the following tools (no filtering):\n")
    for tool in tools:
        lines.append(f"- {tool['name']}: {tool['description']}")
        params = tool.get("parameters", {})
        if params:
            param_summary = ", ".join(f"{k}={v}" for k, v in params.items())
            lines.append(f"  parameters: {param_summary}")
    lines.append(
        "\nDecide which tool to call, with what parameters, and explain your reasoning."
    )
    return "\n".join(lines)


def approximate_token_count(text: str) -> int:
    """
    Rough token count via word-count * 1.3 (typical English ratio for the
    Anthropic / OpenAI tokenizer families). Production should use the real
    tokenizer (e.g. tiktoken or anthropic.Anthropic().count_tokens).
    """
    return int(len(text.split()) * 1.3)


def select(
    query: str, registry_path: str | Path, top_k: int = 5
) -> dict:
    """
    Convenience wrapper that runs the full three-step pipeline and reports
    token-reduction metrics. Returns:
        {
          "query": str,
          "selected": list[{"name", "score", "description"}],
          "baseline_tokens": int,
          "filtered_tokens": int,
          "reduction_pct": float,
        }
    """
    registry = load_registry(registry_path)
    scored = retrieve(query, registry, top_k=top_k)
    validated = validate(scored, query)
    baseline = baseline_prompt(registry, query)
    filtered = invoke_prompt(validated, query)
    bt = approximate_token_count(baseline)
    ft = approximate_token_count(filtered)
    return {
        "query": query,
        "selected": [
            {
                "name": s.tool["name"],
                "score": round(s.score, 3),
                "description": s.tool["description"],
            }
            for s in validated
        ],
        "registry_size": len(registry),
        "baseline_tokens": bt,
        "filtered_tokens": ft,
        "reduction_pct": round(100.0 * (1.0 - ft / max(bt, 1)), 1),
        "baseline_prompt": baseline,
        "filtered_prompt": filtered,
    }
