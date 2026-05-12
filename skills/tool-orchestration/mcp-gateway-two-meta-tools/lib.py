"""
MCP Gateway — two-meta-tool architecture.

Distilled from Agentic Graph RAG (O'Reilly), Chapter 6 — Tool Orchestration.

Writer's production enterprise MCP gateway pattern. Where RAG-MCP retrieves
top-K tools and injects their descriptions into the prompt, the Gateway
pattern keeps tool descriptions OUTSIDE the prompt entirely. The agent sees
exactly two tools:

    search(query, top_k)        -> [tool_name, ...]
    execute(tool_name, **params) -> result

The agent's prompt remains constant regardless of how many tools the gateway
manages (Writer ran this at "hundreds of connectors and thousands of possible
tool calls"). The gateway resolves which underlying tool to invoke.

This module is the reference implementation of the two-meta-tool primitive.
It uses the same word-overlap retriever as the rag-mcp-tool-selection sibling
skill (production: swap for embeddings via the same `score_tool` seam).

Pairs with rag-mcp-tool-selection — they solve the same problem (prompt bloat)
from different angles. Pick the gateway when you want:
- Per-tenant tool segmentation (each customer's agent sees only its slice)
- Per-agent access policies (support agent sees CRM, finance agent sees
  reporting; neither sees the other's tools)
- Constant prompt size regardless of registry growth
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Reuse the retriever from the sibling skill — same seam, same swap point.
# Load via importlib.util to avoid the `lib` module-name collision when both
# this file and the sibling are imported in the same process.
import importlib.util as _ilu
import sys as _sys
_HERE = Path(__file__).resolve().parent
_SIBLING = _HERE.parent / "rag-mcp-tool-selection" / "lib.py"
_MOD_NAME = "rag_mcp_tool_selection_lib"
_spec = _ilu.spec_from_file_location(_MOD_NAME, _SIBLING)
_rag_lib = _ilu.module_from_spec(_spec)
_sys.modules[_MOD_NAME] = _rag_lib  # required so @dataclass can resolve cls.__module__
_spec.loader.exec_module(_rag_lib)


@dataclass
class Gateway:
    """
    A two-meta-tool gateway. The agent only ever calls `search` and `execute`.

    Per-agent access policies are enforced at gateway level: pass an
    `access_filter` callable to limit which tools a given agent role sees.

    Multi-tenant segmentation: instantiate one Gateway per tenant with the
    tenant-scoped registry; the agent never sees other tenants' tools.
    """

    registry: list[dict]
    access_filter: Callable[[dict], bool] | None = None
    _executors: dict[str, Callable[..., Any]] = field(default_factory=dict)

    @classmethod
    def from_registry_file(
        cls, path: str | Path, access_filter: Callable[[dict], bool] | None = None
    ) -> "Gateway":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(registry=data["tools"], access_filter=access_filter)

    def _visible(self) -> list[dict]:
        if self.access_filter is None:
            return self.registry
        return [t for t in self.registry if self.access_filter(t)]

    # ------------------------------------------------------------------
    # The two meta-tools — the entire surface the agent sees
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Meta-tool 1: vector similarity (here: word overlap) over tool metadata.
        Returns a list of {name, score} dicts — descriptions are NOT included.
        """
        visible = self._visible()
        scored = _rag_lib.retrieve(query, visible, top_k=top_k)
        return [{"name": s.tool["name"], "score": round(s.score, 3)} for s in scored]

    def execute(self, tool_name: str, **params: Any) -> dict:
        """
        Meta-tool 2: invoke the chosen tool by name. The gateway resolves
        which underlying executor to call.

        Tools must be registered via `register_executor` before they can be
        called. If no executor is registered, returns a dry-run shape that
        names the tool and echoes the params — useful for demos and tests.
        """
        visible_names = {t["name"] for t in self._visible()}
        if tool_name not in visible_names:
            raise PermissionError(
                f"Tool {tool_name!r} is not visible to this agent "
                f"(access filter rejected it or it is not in the registry)."
            )
        executor = self._executors.get(tool_name)
        if executor is None:
            return {
                "tool": tool_name,
                "params": params,
                "result": "[dry-run — register an executor for live invocation]",
            }
        return {"tool": tool_name, "params": params, "result": executor(**params)}

    # ------------------------------------------------------------------
    # Registration — how the gateway is wired to real backends
    # ------------------------------------------------------------------

    def register_executor(self, tool_name: str, fn: Callable[..., Any]) -> None:
        """Bind a real backend (boto3 call, HTTP request, MCP forward) to a tool."""
        if not any(t["name"] == tool_name for t in self.registry):
            raise KeyError(f"Tool {tool_name!r} is not in the registry.")
        self._executors[tool_name] = fn

    # ------------------------------------------------------------------
    # Prompt-budget accounting — how much the gateway saves vs RAG-MCP
    # ------------------------------------------------------------------

    def agent_prompt(self, query: str) -> str:
        """
        What the agent sees: the query plus the two meta-tool signatures.
        Independent of registry size — that's the architectural point.
        """
        return (
            f"You are a DevOps agent. The user's query: {query!r}\n\n"
            "You have exactly two tools:\n"
            "  - search(query: str, top_k: int = 5) -> list[{name, score}]\n"
            "    Search the gateway for relevant tools by natural-language query.\n"
            "  - execute(tool_name: str, **params) -> {tool, params, result}\n"
            "    Invoke the chosen tool by name with appropriate parameters.\n\n"
            "Start by calling search() to find relevant tools, then execute() the best match."
        )


def example_access_filter_devops(tool: dict) -> bool:
    """
    Example access filter — a DevOps agent role sees only ops-relevant tools.
    Production: drive this from your IAM/RBAC layer.
    """
    devops_topics = {
        "logs", "metrics", "tracing", "deployment", "containers",
        "load-balancer", "investigation", "monitoring", "rollback",
        "incident-response", "remediation", "ec2", "ecs", "lambda",
        "cloudtrail", "audit", "session-manager", "queues", "consumer-lag",
        "throttling", "stages", "step-functions", "workflows",
        "configuration", "database", "logs", "slow-queries",
    }
    topics = set(tool.get("key_topics", []))
    return bool(topics & devops_topics)
