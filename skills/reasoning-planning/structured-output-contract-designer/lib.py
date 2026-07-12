"""
Structured-output contract design for graph-agent node seams, distilled from
Ch5 "Structured Generation: The Keystone of Reliable Communication" (Outlines).

The chapter's claim: most graph-agent failures are internode COMMUNICATION
breakdowns, not bad reasoning. A node that emits free text is unreliable at the
seam where its output feeds the next node or a graph write. Constraining
generation to a schema/grammar (Outlines builds a finite-state machine over
valid token sequences and zeros out any token that would leave the valid set)
makes the seam reliable BY CONSTRUCTION, not by post-hoc validation that can be
bypassed or fail silently. Structure then compounds with the graph: internode
contracts become unbreakable and reasoning becomes composable.

This module picks an ENFORCEMENT LEVEL per node from its seam profile, emits a
minimal contract for common DevOps-investigation node types, and validates a
payload against a contract deterministically (the "seam is verifiable" primitive).

Pure Python, stdlib only. No model / Outlines runtime required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


# Three enforcement levels, ordered by constraint strength.
LEVELS = ("FREE_TEXT", "JSON_SCHEMA", "GRAMMAR_CONSTRAINED")
LEVEL_STRENGTH = {"FREE_TEXT": 0, "JSON_SCHEMA": 1, "GRAMMAR_CONSTRAINED": 2}

# Who consumes the node's output. Only a human terminal reader tolerates prose.
CONSUMERS = ("human", "next_node", "graph_write", "tool_call")


@dataclass
class NodeProfile:
    """The seam profile of one graph node's output.

    consumed_by: human | next_node | graph_write | tool_call. Anything other
        than a human terminal reader is a machine seam that must parse.
    needs_valid_parse: the consumer must deterministically parse the output.
    fixed_vocabulary: the output must draw from a closed set / match a formal
        grammar / land on a specific graph node-type. Triggers a grammar.
    reliability_criticality: 0..3 how costly a malformed output is (compliance,
        graph corruption, wrong tool call).
    latency_budget: 0..3 slack for generation cost. Lower = tighter; used only
        to price OVER-constraint, never to under-constrain a machine seam.
    """
    consumed_by: str = "next_node"
    needs_valid_parse: bool = True
    fixed_vocabulary: bool = False
    reliability_criticality: int = 1
    latency_budget: int = 2


def _required_strength(profile: NodeProfile) -> int:
    """The MINIMUM enforcement strength the seam requires.

    Rules (Ch5): a fixed vocabulary / node-type target needs a grammar; any
    node-to-node, graph-write, or tool-call seam needs at least a JSON schema;
    free text is admissible only for a human terminal reader that is not
    reliability-critical and does not need a valid parse.
    """
    if profile.fixed_vocabulary:
        return LEVEL_STRENGTH["GRAMMAR_CONSTRAINED"]
    if profile.consumed_by in ("next_node", "graph_write", "tool_call"):
        return LEVEL_STRENGTH["JSON_SCHEMA"]
    # consumed_by == human
    if profile.needs_valid_parse or profile.reliability_criticality >= 2:
        return LEVEL_STRENGTH["JSON_SCHEMA"]
    return LEVEL_STRENGTH["FREE_TEXT"]


def _score_levels(profile: NodeProfile) -> Dict[str, float]:
    """Score each level. Under-constraint (unreliable seam) is penalized hard;
    over-constraint is priced mildly against the latency budget. The level that
    exactly meets the required strength scores highest, so argmax == the rule
    result and the scores explain the choice.
    """
    req = _required_strength(profile)
    over_penalty = 0.5 if profile.latency_budget <= 1 else 0.25
    scores: Dict[str, float] = {}
    for level, strength in LEVEL_STRENGTH.items():
        if strength < req:
            scores[level] = -10.0 * float(req - strength)
        else:
            scores[level] = 10.0 - over_penalty * float(strength - req)
    return scores


_RATIONALE = {
    "FREE_TEXT": ("Terminal human-facing prose. No downstream parser, so a "
                  "schema would only add latency. Admissible ONLY when the "
                  "reader is human and the output is not reliability-critical."),
    "JSON_SCHEMA": ("Node-to-node / graph-write / tool-call seam. A JSON schema "
                    "makes the contract parseable by construction so the next "
                    "node relies on the shape instead of defensively parsing "
                    "prose (Outlines enforces the schema at the token level)."),
    "GRAMMAR_CONSTRAINED": ("Output must match a formal grammar, a closed "
                            "vocabulary, or a specific graph node-type. A "
                            "grammar makes any out-of-vocabulary / off-type "
                            "token sequence physically ungenerable."),
}


def recommend_enforcement(profile: NodeProfile) -> Dict[str, Any]:
    """Pick an enforcement level for a node's output seam and explain it.

    Returns {recommended, rationale, scores}. The recommended level is the one
    whose constraint strength exactly meets the seam's requirement.
    """
    scores = _score_levels(profile)
    recommended = max(scores, key=lambda lvl: scores[lvl])
    return {
        "recommended": recommended,
        "rationale": _RATIONALE[recommended],
        "scores": scores,
    }


# ---------------------------------------------------------------------------
# Node-type contracts. Minimal JSON-schema-like dicts for common DevOps
# investigation node types (Ch5 DevOps latency scenario + the reasoning /
# planning / action / validation node roles Outlines constrains).
# ---------------------------------------------------------------------------

_NODE_TYPE_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "hypothesis": {
        "required": ["id", "statement", "confidence", "evidence"],
        "types": {"id": "str", "statement": "str",
                  "confidence": "float", "evidence": "list"},
        "enums": {},
    },
    "remediation": {
        "required": ["action", "risk", "rollback"],
        "types": {"action": "str", "risk": "str", "rollback": "str"},
        "enums": {"risk": ["low", "medium", "high"]},
    },
    "reasoning": {
        "required": ["premises", "inference_steps", "conclusion", "confidence"],
        "types": {"premises": "list", "inference_steps": "list",
                  "conclusion": "str", "confidence": "float"},
        "enums": {},
    },
    "validation": {
        "required": ["violation_type", "severity", "remediation"],
        "types": {"violation_type": "str", "severity": "str",
                  "remediation": "str"},
        "enums": {"severity": ["info", "warning", "error", "critical"]},
    },
}


def node_types() -> List[str]:
    return sorted(_NODE_TYPE_CONTRACTS)


def schema_from_node_type(node_type: str) -> Dict[str, Any]:
    """Emit a minimal contract dict (required fields + types + closed-vocabulary
    enums) for a known DevOps investigation node type. The enum'd fields are the
    ones whose seam warrants GRAMMAR_CONSTRAINED enforcement.
    """
    if node_type not in _NODE_TYPE_CONTRACTS:
        raise KeyError(
            f"unknown node_type {node_type!r}; known: {node_types()}")
    contract = _NODE_TYPE_CONTRACTS[node_type]
    # Return a fresh copy so callers cannot mutate the registry.
    return {
        "node_type": node_type,
        "required": list(contract["required"]),
        "types": dict(contract["types"]),
        "enums": {k: list(v) for k, v in contract["enums"].items()},
    }


# Map contract type names to Python type predicates. bool is excluded from the
# numeric types even though it subclasses int, so a stray flag is caught.
def _type_ok(value: Any, type_name: str) -> bool:
    if type_name == "str":
        return isinstance(value, str)
    if type_name == "bool":
        return isinstance(value, bool)
    if type_name == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "list":
        return isinstance(value, list)
    if type_name == "dict":
        return isinstance(value, dict)
    # Unknown type name: cannot validate, treat as violation.
    return False


def validate_against_contract(payload: Dict[str, Any],
                              contract: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministically validate a payload against a contract.

    Checks, in order: every required field present, each field's type matches,
    each enum'd field draws from its closed vocabulary. This is the primitive
    that makes a structured seam VERIFIABLE at the receiving node.

    Returns {valid: bool, violations: [str, ...]}.
    """
    violations: List[str] = []
    required = contract.get("required", [])
    types = contract.get("types", {})
    enums = contract.get("enums", {})

    for field in required:
        if field not in payload:
            violations.append(f"missing required field: {field}")

    for field, type_name in types.items():
        if field in payload and not _type_ok(payload[field], type_name):
            got = type(payload[field]).__name__
            violations.append(
                f"type mismatch on {field}: expected {type_name}, got {got}")

    for field, vocabulary in enums.items():
        if field in payload and payload[field] not in vocabulary:
            violations.append(
                f"vocabulary violation on {field}: {payload[field]!r} "
                f"not in {vocabulary}")

    return {"valid": not violations, "violations": violations}


def reliability_gain(free_text_parse_rate: float,
                     constrained_parse_rate: float = 1.0) -> Dict[str, Any]:
    """Make the keystone claim concrete: the seam reliability delta from
    switching a node to constrained decoding. Ch5: even a 0.1% malformed rate
    is compliance exposure at scale; structured generation drives it to zero.
    """
    before_fail = 1.0 - free_text_parse_rate
    after_fail = 1.0 - constrained_parse_rate
    return {
        "free_text_parse_rate": free_text_parse_rate,
        "constrained_parse_rate": constrained_parse_rate,
        "absolute_gain": constrained_parse_rate - free_text_parse_rate,
        "failure_rate_before": before_fail,
        "failure_rate_after": after_fail,
        "failures_eliminated_per_million": round((before_fail - after_fail) * 1_000_000),
    }
