"""
Information Flow Control gate — type-matched tool chaining + taint tracking.

Distilled from Agentic Graph RAG (O'Reilly), Chapter 6 — Tool Orchestration
("Tool Dependencies and Type Matching" + "Securing Data Flow with Information
Flow Control").

Two problems, one gate:

1. TYPE MATCHING (NESTFUL benchmark: even advanced LLMs hit only ~41% success
   on nested API calls when tool relationships are implicit). Tools declare the
   types they REQUIRE as input and PRODUCE as output. A dependency chain is any
   path where one tool's output type matches another tool's input type. The
   canonical example: get_covid_stats REQUIRES a location of type
   ISO_3166_1_alpha_2; get_country_details PRODUCES a short_name of that type;
   the shared type connects them, so "COVID stats for India" resolves to
   [get_country_details("India") -> "IN", get_covid_stats(location="IN")].

2. TAINT TRACKING (FIDES). Every value carries a trust label based on its
   provenance. Internal-domain data is TRUSTED, external data is UNTRUSTED. The
   taint propagates through operations: mixing trusted with untrusted yields
   UNTRUSTED. A deterministic policy then blocks sensitive actions on tainted
   data. Opaque-variable management hardens this further: the LLM never sees raw
   untrusted content, only an opaque reference (a UUID); to read the content it
   must call read_variable, which keeps the taint policy in force.

This gate is a deterministic security-policy LAYER. It answers questions
authentication cannot: not "is this agent allowed to call this tool" but "is
this DATA allowed to flow into this action".

STDLIB ONLY.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


# ----------------------------------------------------------------------------
# Part 1 — Tool dependencies and type matching
# ----------------------------------------------------------------------------

def load_tool_specs(path: str | Path) -> list[dict]:
    """
    Load tool dependency specs. Each spec:
        {
          "name": "get_covid_stats",
          "requires": [{"parameter": "location", "type": "ISO_3166_1_alpha_2"}],
          "produces": [{"field": "cases", "type": "Integer"}]
        }
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["tools"]


@dataclass(frozen=True)
class DependencyEdge:
    producer: str
    consumer: str
    shared_type: str
    produces_field: str
    requires_parameter: str


def match_dependencies(tools: Iterable[dict]) -> list[DependencyEdge]:
    """
    Discover every producer->consumer edge where an output type matches an
    input type (chapter Example 6-5: MATCH path where PRODUCES_OUTPUT type ==
    REQUIRES_INPUT type). This reduces a multi-step reasoning task to a graph
    traversal.
    """
    tools = list(tools)
    edges: list[DependencyEdge] = []
    for producer in tools:
        for out in producer.get("produces", []):
            for consumer in tools:
                if consumer["name"] == producer["name"]:
                    continue
                for req in consumer.get("requires", []):
                    if out["type"] == req["type"]:
                        edges.append(
                            DependencyEdge(
                                producer=producer["name"],
                                consumer=consumer["name"],
                                shared_type=out["type"],
                                produces_field=out["field"],
                                requires_parameter=req["parameter"],
                            )
                        )
    return edges


def plan_execution(
    tools: Iterable[dict], target_tool: str, available_types: set[str]
) -> list[dict]:
    """
    Given the types the caller already has (available_types) and a target tool,
    return an ordered execution plan that satisfies the target's required input
    types, inserting the producer tools needed to bridge missing types.

    Deterministic pathfinding over the type graph — the chapter's answer to the
    NESTFUL failure mode (LLMs failing to recognize that getting COVID stats for
    a country requires first obtaining the country code).

    # TODO(production): handle multi-hop chains (A produces X, B needs X and
    # produces Y, C needs Y) via a full topological sort. This resolves the
    # single-hop bridge, which covers the chapter's worked examples.
    """
    tools = list(tools)
    by_name = {t["name"]: t for t in tools}
    if target_tool not in by_name:
        raise KeyError(f"Target tool {target_tool!r} not in specs.")
    target = by_name[target_tool]
    have = set(available_types)
    plan: list[dict] = []

    for req in target.get("requires", []):
        rtype = req["type"]
        if rtype in have:
            plan.append({"tool": target_tool, "parameter": req["parameter"],
                         "type": rtype, "source": "already-available"})
            continue
        # Find a producer of the missing type.
        producer = None
        for t in tools:
            if t["name"] == target_tool:
                continue
            if any(o["type"] == rtype for o in t.get("produces", [])):
                producer = t
                break
        if producer is None:
            plan.append({"tool": target_tool, "parameter": req["parameter"],
                         "type": rtype, "source": "UNRESOLVED"})
            continue
        field = next(o["field"] for o in producer["produces"] if o["type"] == rtype)
        plan.append({"tool": producer["name"], "produces_field": field,
                     "type": rtype, "source": "bridge-producer",
                     "feeds": {"tool": target_tool, "parameter": req["parameter"]}})
        have.add(rtype)
    # The target call itself, last.
    plan.append({"tool": target_tool, "step": "invoke", "requires": [
        r["parameter"] for r in target.get("requires", [])]})
    return plan


# ----------------------------------------------------------------------------
# Part 2 — Taint tracking (FIDES IFC labels)
# ----------------------------------------------------------------------------

class Label(str, Enum):
    TRUSTED = "TRUSTED"
    UNTRUSTED = "UNTRUSTED"


@dataclass(frozen=True)
class TaintedValue:
    value: Any
    label: Label
    source: str

    def is_trusted(self) -> bool:
        return self.label is Label.TRUSTED


# Actions the policy treats as sensitive — never permitted on tainted (UNTRUSTED)
# data. The chapter's worked case is an email summarizer that must not take a
# sensitive action when the summary inherited an UNTRUSTED label.
SENSITIVE_ACTIONS = frozenset(
    {"send_email", "delete", "execute_code", "transfer_funds",
     "modify_permissions", "external_post", "run_shell"}
)


def label_by_source(value: Any, source: str, trusted_domains: Iterable[str]) -> TaintedValue:
    """
    Assign a trust label from provenance. Data from an internal/allowlisted
    source domain is TRUSTED; everything else is UNTRUSTED (FIDES: an email from
    an internal domain is TRUSTED, an external one UNTRUSTED).

    # TODO(production): drive trusted_domains from the org's IAM/allowlist and
    # match on verified sender identity, not a substring — this is a demo check.
    """
    trusted = {d.lower() for d in trusted_domains}
    src = source.lower()
    is_trusted = any(src.endswith(d) or src == d for d in trusted)
    return TaintedValue(
        value=value,
        label=Label.TRUSTED if is_trusted else Label.UNTRUSTED,
        source=source,
    )


def propagate(inputs: Iterable[TaintedValue]) -> Label:
    """
    Taint propagation: if trusted data is mixed with untrusted data, the result
    inherits the UNTRUSTED label (FIDES). Any single untrusted input taints the
    whole output.
    """
    inputs = list(inputs)
    if not inputs:
        return Label.TRUSTED
    return Label.UNTRUSTED if any(not v.is_trusted() for v in inputs) else Label.TRUSTED


def check_policy(action: str, result_label: Label) -> dict:
    """
    Deterministic security policy: block a sensitive action on tainted data.
    Returns {allowed, reason}. This is the deterministic layer the chapter
    describes — a policy decision, not an LLM judgment.
    """
    sensitive = action in SENSITIVE_ACTIONS
    if sensitive and result_label is Label.UNTRUSTED:
        return {
            "allowed": False,
            "action": action,
            "label": result_label.value,
            "reason": f"sensitive action {action!r} blocked on UNTRUSTED data",
        }
    return {
        "allowed": True,
        "action": action,
        "label": result_label.value,
        "reason": "permitted"
        + ("" if not sensitive else " (sensitive action on TRUSTED data)"),
    }


def evaluate_flow(flow: dict, trusted_domains: Iterable[str]) -> dict:
    """
    End-to-end evaluation of a data flow: label each input by source, propagate
    the combined taint, and check the flow's action against the policy.

    A flow:
        {
          "name": "summarize-and-email",
          "action": "send_email",
          "inputs": [
             {"value": "...", "source": "internal.acme.com"},
             {"value": "...", "source": "external-sender.net"}
          ]
        }
    """
    labeled = [
        label_by_source(i["value"], i["source"], trusted_domains)
        for i in flow.get("inputs", [])
    ]
    result_label = propagate(labeled)
    decision = check_policy(flow["action"], result_label)
    return {
        "flow": flow.get("name", "unnamed"),
        "action": flow["action"],
        "inputs": [
            {"source": v.source, "label": v.label.value} for v in labeled
        ],
        "propagated_label": result_label.value,
        "decision": decision,
    }


# ----------------------------------------------------------------------------
# Part 3 — Opaque variable management
# ----------------------------------------------------------------------------

@dataclass
class OpaqueStore:
    """
    FIDES opaque-variable management. The LLM never sees raw untrusted content;
    it is given an opaque reference (a UUID). To access the content the agent
    must call read_variable, which keeps taint tracking in force and prevents
    malicious instructions embedded in the content from directly steering the
    LLM's reasoning.
    """

    _store: dict[str, TaintedValue] = field(default_factory=dict)
    _reads: list[str] = field(default_factory=list)

    def put(self, value: Any, label: Label, source: str) -> str:
        """Store a value; return an opaque UUID reference (what the LLM sees)."""
        ref = str(uuid.uuid4())
        self._store[ref] = TaintedValue(value=value, label=label, source=source)
        return ref

    def read_variable(self, ref: str) -> TaintedValue:
        """
        Explicit accessor — the ONLY way to dereference content. Every read is
        recorded so the taint policy can audit which untrusted content was
        materialized and where.
        """
        if ref not in self._store:
            raise KeyError(f"Unknown opaque reference {ref!r}")
        self._reads.append(ref)
        return self._store[ref]

    def read_log(self) -> list[str]:
        return list(self._reads)


def load_flows(path: str | Path) -> list[dict]:
    """Load sample data-flow scenarios for taint evaluation."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["flows"]
