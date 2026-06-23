"""
HINDSIGHT 4-network epistemic classifier (Ch4).

Routes facts to World / Experience / Opinion / Observation per Latimer et al.
2025 §3.4. Heuristic-based default; production swap to LLM-typed-output
classifier at the seam noted below.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


NETWORK_WORLD = "World"
NETWORK_EXPERIENCE = "Experience"
NETWORK_OPINION = "Opinion"
NETWORK_OBSERVATION = "Observation"
NETWORKS = (NETWORK_WORLD, NETWORK_EXPERIENCE, NETWORK_OPINION, NETWORK_OBSERVATION)


@dataclass
class EpistemicFact:
    text: str
    network: str
    confidence: float = 1.0                 # only meaningful for Opinion / Observation
    timestamp: Optional[datetime] = None    # required for Experience
    source: Optional[str] = None            # agent | external | system
    external_ref: Optional[str] = None      # URL / doc / system source for World
    inferred_from: List[str] = field(default_factory=list)   # Opinion provenance
    derived_from: List[str] = field(default_factory=list)    # Observation provenance
    action_type: Optional[str] = None       # Experience: tool call / API call / inference step

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("timestamp"):
            d["timestamp"] = d["timestamp"].isoformat()
        return d


# ---------------------------------------------------------------------------
# Heuristic signals
# ---------------------------------------------------------------------------

FIRST_PERSON_PATTERNS = [
    r"\bI (called|invoked|retrieved|fetched|sent|wrote|received|noticed|computed|decided|started|finished)\b",
    r"\bI'm \w+ing\b",
    r"\bI've (called|retrieved|invoked|done)\b",
]
HEDGING_PATTERNS = [
    r"\b(I (believe|think|suspect))\b",
    r"\b(likely|probably|appears? to|seems? to|might|may|could be)\b",
    r"\b(I'm not sure|uncertain|unclear)\b",
    r"\bconfidence[: ]\s*0?\.\d+\b",
]
SYNTHESIS_PATTERNS = [
    r"\b(based on|in summary|to summari[sz]e|overall|in aggregate)\b",
    r"\b(derived from|synthesized from|combining)\b",
]


def _matches_any(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


# ---------------------------------------------------------------------------
# Classify
# ---------------------------------------------------------------------------

def classify(
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    confidence: Optional[float] = None,
) -> EpistemicFact:
    """Classify a fact into one of the 4 networks.

    Order matters: Experience (first-person + action_type) > Opinion (hedging
    or explicit confidence < 1) > Observation (synthesis + multi-source) >
    World (default).
    """
    metadata = metadata or {}

    # 1. Experience — first-person action, optionally with metadata source==agent
    is_first_person = _matches_any(text, FIRST_PERSON_PATTERNS)
    is_agent_action = metadata.get("source") == "agent" or metadata.get("action_type")
    if is_first_person or is_agent_action:
        ts = metadata.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return EpistemicFact(
            text=text,
            network=NETWORK_EXPERIENCE,
            timestamp=ts,
            source="agent",
            action_type=metadata.get("action_type"),
        )

    # 2. Opinion — hedging language or explicit confidence < 1
    is_hedging = _matches_any(text, HEDGING_PATTERNS)
    conf_from_arg = confidence if confidence is not None else metadata.get("confidence", 1.0)
    is_low_confidence = conf_from_arg < 1.0
    if is_hedging or is_low_confidence:
        return EpistemicFact(
            text=text,
            network=NETWORK_OPINION,
            confidence=min(conf_from_arg, 0.95) if is_hedging and conf_from_arg == 1.0 else conf_from_arg,
            inferred_from=metadata.get("inferred_from", []),
        )

    # 3. Observation — synthesis language + multiple derived_from refs
    is_synthesis = _matches_any(text, SYNTHESIS_PATTERNS)
    derived = metadata.get("derived_from", [])
    if is_synthesis or len(derived) >= 2:
        return EpistemicFact(
            text=text,
            network=NETWORK_OBSERVATION,
            confidence=conf_from_arg,
            derived_from=derived,
        )

    # 4. World — default, declarative
    return EpistemicFact(
        text=text,
        network=NETWORK_WORLD,
        external_ref=metadata.get("external_ref"),
    )


def classify_batch(facts: List[Dict[str, Any]]) -> List[EpistemicFact]:
    """Each input is {text, metadata?, confidence?}."""
    return [
        classify(f["text"], metadata=f.get("metadata"), confidence=f.get("confidence"))
        for f in facts
    ]


# ---------------------------------------------------------------------------
# Justify — provenance chain for Opinion / Observation
# ---------------------------------------------------------------------------

def justify(facts: List[EpistemicFact], query_text: str) -> Dict[str, Any]:
    """For a target Opinion/Observation fact, return the World/Experience
    facts it traces back to."""
    target = next((f for f in facts if f.text == query_text), None)
    if target is None:
        return {"target": query_text, "found": False}
    if target.network == NETWORK_WORLD:
        return {"target": query_text, "network": "World",
                "provenance": "external", "external_ref": target.external_ref}
    if target.network == NETWORK_EXPERIENCE:
        return {"target": query_text, "network": "Experience",
                "provenance": "agent-action",
                "timestamp": target.timestamp.isoformat() if target.timestamp else None}
    refs = target.inferred_from if target.network == NETWORK_OPINION else target.derived_from
    grounding = []
    for ref in refs:
        ref_fact = next((f for f in facts if f.text == ref), None)
        if ref_fact:
            grounding.append({"text": ref_fact.text, "network": ref_fact.network})
        else:
            grounding.append({"text": ref, "network": "unknown (orphan)"})
    return {
        "target": query_text,
        "network": target.network,
        "confidence": target.confidence,
        "provenance": grounding,
    }


# ---------------------------------------------------------------------------
# Network audit
# ---------------------------------------------------------------------------

def network_audit(facts: List[EpistemicFact]) -> Dict[str, Any]:
    counts = {n: 0 for n in NETWORKS}
    experience_without_ts = 0
    orphan_opinions = 0
    orphan_observations = 0
    world_with_low_confidence = 0
    for f in facts:
        counts[f.network] = counts.get(f.network, 0) + 1
        if f.network == NETWORK_EXPERIENCE and f.timestamp is None:
            experience_without_ts += 1
        if f.network == NETWORK_OPINION and not f.inferred_from:
            orphan_opinions += 1
        if f.network == NETWORK_OBSERVATION and not f.derived_from:
            orphan_observations += 1
        if f.network == NETWORK_WORLD and f.confidence < 1.0:
            world_with_low_confidence += 1
    warnings = []
    if experience_without_ts > 0:
        warnings.append(f"{experience_without_ts} Experience facts have no timestamp")
    if orphan_opinions > 0:
        warnings.append(f"{orphan_opinions} Opinion facts have no inferred_from provenance chain")
    if orphan_observations > 0:
        warnings.append(f"{orphan_observations} Observation facts have no derived_from chain")
    if world_with_low_confidence > 0:
        warnings.append(f"{world_with_low_confidence} World facts have confidence < 1.0 (likely misclassified Opinion)")
    return {
        "counts": counts,
        "total": len(facts),
        "warnings": warnings,
    }
