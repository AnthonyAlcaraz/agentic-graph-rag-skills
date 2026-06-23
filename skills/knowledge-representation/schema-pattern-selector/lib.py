"""
Schema Design Pattern selector + validator (Ch3 "Schema Design Patterns").

Four patterns, each addressing a distinct agent-reasoning dimension:

  event_centric        temporal reasoning, cause/effect, sequence
  contextual_boundary  scope/validity boundaries, prevent context mixing
  multi_perspective    contradictory viewpoints with attribution + confidence
  capability_model     agent self-awareness of capabilities + limits/authority

The selector maps a described "knowledge shape" to the pattern(s) that fit.
The validator checks that an instance of a pattern carries its required
relationships/fields (e.g. an event must have temporal connections; a
multi-perspective statement must attribute each value to a source with
confidence). Patterns compose (Ch3 Tip: event-centric can carry
multi-perspective elements, capability bounded by contextual constraints).

Pure Python, stdlib only.
"""

from __future__ import annotations

from typing import Any, Dict, List


PATTERNS = ("event_centric", "contextual_boundary", "multi_perspective",
            "capability_model")

# Signal -> pattern. Each pattern's defining signals, distilled from the
# section's prose. A knowledge shape that exhibits a signal points at the
# pattern.
PATTERN_SIGNALS: Dict[str, List[str]] = {
    "event_centric": [
        "temporal", "time", "sequence", "before", "after", "cause", "effect",
        "occurrence", "deployment", "meeting", "happened", "timestamp", "history",
    ],
    "contextual_boundary": [
        "scope", "boundary", "valid_during", "applies_to", "environment",
        "context_mixing", "project", "team_specific", "time_range", "tenant",
    ],
    "multi_perspective": [
        "contradiction", "conflicting", "disagree", "perspective", "viewpoint",
        "according_to", "source", "confidence", "drift", "divergent", "forecast",
    ],
    "capability_model": [
        "capability", "authorization", "permission", "limit", "can_do",
        "escalate", "authority", "operational_boundary", "self_aware", "allowed",
    ],
}

# Required fields/relationships per pattern (the validator contract).
PATTERN_CONTRACT: Dict[str, Dict[str, Any]] = {
    "event_centric": {
        "required_relationships": ["hasParticipant"],
        "temporal_relationships_any": ["hasStartTime", "hasEndTime",
                                       "hasPrecedingEvent", "hasFollowingEvent"],
        "note": "event must be a first-class node with at least one temporal link",
    },
    "contextual_boundary": {
        "required_relationships": ["contains"],
        "boundary_relationships_any": ["validDuring", "appliesTo"],
        "note": "context must declare at least one scope boundary (temporal or organizational)",
    },
    "multi_perspective": {
        "required_relationships": ["according-to"],
        "perspective_fields": ["source", "confidence"],
        "note": "every perspective must attribute a value to a source with confidence",
    },
    "capability_model": {
        "required_relationships": ["hasCapability"],
        "capability_fields": ["type", "authorization-level"],
        "note": "each capability must declare requirements and authorization level",
    },
}


def select_patterns(shape_description: str) -> List[Dict[str, Any]]:
    """Score patterns against a free-text description of the knowledge shape.

    Returns [{pattern, score, matched_signals}, ...] sorted by score desc.
    Score = count of distinct signal tokens found in the description.
    """
    text = shape_description.lower()
    results = []
    for pattern, signals in PATTERN_SIGNALS.items():
        matched = sorted({s for s in signals if s.replace("_", " ") in text
                          or s in text})
        results.append({
            "pattern": pattern,
            "score": len(matched),
            "matched_signals": matched,
        })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def recommend_pattern(shape_description: str) -> Dict[str, Any]:
    """Pick the top pattern, flag composition when 2+ patterns score > 0."""
    scored = select_patterns(shape_description)
    top = scored[0]
    composed = [r["pattern"] for r in scored if r["score"] > 0]
    out = {
        "recommended": top["pattern"] if top["score"] > 0 else None,
        "scores": {r["pattern"]: r["score"] for r in scored},
        "contract": PATTERN_CONTRACT.get(top["pattern"]) if top["score"] > 0 else None,
    }
    if len(composed) >= 2:
        out["compose"] = composed
        out["compose_note"] = (
            "Multiple patterns fit. Ch3 Tip: combine them -- e.g. an "
            "event-centric node can carry multi-perspective viewpoints, a "
            "capability can be bounded by contextual constraints."
        )
    return out


def validate_instance(pattern: str, instance: Dict[str, Any]) -> Dict[str, Any]:
    """Validate that a pattern instance carries its required relationships/fields.

    instance shape: {"relationships": {rel_type: [targets...]}, "perspectives":
    [...], "capabilities": [...]} (only the keys relevant to the pattern matter).

    Returns {valid: bool, errors: [...], pattern: ...}.
    """
    if pattern not in PATTERN_CONTRACT:
        raise ValueError(f"unknown pattern '{pattern}'")
    contract = PATTERN_CONTRACT[pattern]
    errors: List[str] = []
    rels = instance.get("relationships", {})

    for req in contract.get("required_relationships", []):
        if req not in rels or not rels[req]:
            errors.append(f"missing required relationship '{req}'")

    if pattern == "event_centric":
        temporal_any = contract["temporal_relationships_any"]
        if not any(t in rels and rels[t] for t in temporal_any):
            errors.append(
                "event has no temporal link; needs at least one of "
                + ", ".join(temporal_any)
            )

    if pattern == "contextual_boundary":
        boundary_any = contract["boundary_relationships_any"]
        if not any(b in rels and rels[b] for b in boundary_any):
            errors.append(
                "context declares no scope boundary; needs at least one of "
                + ", ".join(boundary_any)
            )

    if pattern == "multi_perspective":
        perspectives = instance.get("perspectives", [])
        if not perspectives:
            errors.append("multi-perspective statement has no perspectives")
        for i, p in enumerate(perspectives):
            for fld in contract["perspective_fields"]:
                if fld not in p:
                    errors.append(f"perspective[{i}] missing '{fld}'")
            if "confidence" in p:
                c = p["confidence"]
                if not isinstance(c, (int, float)) or not (0.0 <= c <= 1.0):
                    errors.append(f"perspective[{i}] confidence {c} not in [0,1]")

    if pattern == "capability_model":
        caps = instance.get("capabilities", [])
        if not caps:
            errors.append("agent declares no capabilities")
        for i, cap in enumerate(caps):
            for fld in contract["capability_fields"]:
                if fld not in cap:
                    errors.append(f"capability[{i}] missing '{fld}'")

    return {"valid": not errors, "errors": errors, "pattern": pattern}
