"""
Four-layer evaluation cascade primitive (Ch7).

A sequential diagnostic cascade that autopsies one agent execution. It moves
from the most general failure cause to the most specific, STOPPING at the first
layer that catches the failure. Each layer answers a progressively narrower
question (Ch7 Figure 7-1):

- Layer 0: is the answer grounded in the retrieved premise? (zero-shot NLI gate)
- Layer 1: did the agent even possess the information it needed? (context)
- Layer 2: knowledge failure or reasoning failure? (cognitive fault isolator)
- Layer 3: are the quantitative claims actually correct? (tool-integrated judge)

Production swap: every layer here is a deterministic dev-time stand-in for an
LLM / model / code-executor component. The public API (dataclass shapes +
function signatures) is the stable seam; each internal heuristic is marked with
a `# TODO(production): ...` naming the component to swap in. Layer 0 wants a
GLiClass / DeBERTa NLI classifier; Layer 1 wants a Meta J1 reasoning-trace
judge; Layer 3 wants a TIR-Judge CodeExecutor generating Cypher against the KG.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# -- recommended-intervention vocabulary (Ch7 diagnostic-report vocabulary) ------------
BLOCK_AND_REGENERATE = "BLOCK_AND_REGENERATE"
RETRIEVAL_FIX = "RETRIEVAL_FIX"
PROMPT_REFINEMENT = "PROMPT_REFINEMENT"
FINE_TUNE = "FINE_TUNE"
NONE = "NONE"

# -- gate action vocabulary (Ch7 J1 judge example + SLM-LLM flywheel) -------------
PROCEED = "PROCEED"
ESCALATE = "ESCALATE"

# Escalation floor: scores in [ESCALATE_FLOOR, threshold) escalate to the full
# pipeline rather than hard-blocking (Ch7 SLM-LLM flywheel, 0.5-0.85 band).
ESCALATE_FLOOR = 0.5

_TOKEN_RE = re.compile(r"[A-Za-z0-9_.\-]+")
_ENTITY_RE = re.compile(r"[\d_.\-]")

STOPWORDS = frozenset({
    "the", "a", "an", "of", "to", "in", "on", "and", "or", "via", "is", "are",
    "was", "were", "be", "been", "with", "for", "from", "by", "at", "as", "it",
    "its", "that", "this", "these", "those", "will", "would", "does", "did",
    "has", "have", "had", "but", "not", "no", "any", "all", "which", "what",
    "if", "then", "so", "into", "using", "used", "use", "uses",
})


def _tokens(text: str) -> List[str]:
    out: List[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        tok = raw.strip("._-")
        if tok:
            out.append(tok)
    return out


def _content_tokens(text: str) -> List[str]:
    return [t for t in _tokens(text) if t not in STOPWORDS]


def _is_entity(token: str) -> bool:
    return bool(_ENTITY_RE.search(token))


# ===========================================================================
# Layer 0: zero-shot hallucination gate
# ===========================================================================

@dataclass
class GateResult:
    passed: bool
    confidence: float
    action: str
    skip_full_eval: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def layer0_hallucination_gate(
    query: str,
    answer: str,
    context_premise: str,
    threshold: float = 0.85,
) -> GateResult:
    """Layer 0: prescreen the answer for grounding before the expensive layers.

    Deterministic grounding heuristic: the fraction of the answer's content
    tokens that are supported by the premise, multiplied by the fraction of
    entity-level tokens (service names, versions, API identifiers) present in
    the premise. An entity-level claim absent from the premise drives the score
    toward 0, which is the batch_charge failure mode from Ch7: the agent claims
    an edge the graph does not contain.

    Scoring bands (Ch7 J1 judge example + SLM-LLM flywheel):
      score >= threshold     -> passed, PROCEED
      ESCALATE_FLOOR..thresh -> not passed, ESCALATE to full pipeline (no block)
      score < ESCALATE_FLOOR -> not passed, BLOCK_AND_REGENERATE, skip full eval

    # TODO(production): swap heuristic for GLiClass / DeBERTa NLI classifier
    scoring premise=materialized_subgraph, hypothesis=answer.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0, 1], got {threshold}")
    premise_l = context_premise.lower()
    content = _content_tokens(answer)
    if not content:
        raise ValueError("answer has no content tokens to ground")

    supported = [t for t in content if t in premise_l]
    overall = len(supported) / len(content)

    entities = [t for t in content if _is_entity(t)]
    if entities:
        supported_entities = [t for t in entities if t in premise_l]
        entity_score = len(supported_entities) / len(entities)
        score = overall * entity_score
    else:
        score = overall

    score = round(score, 4)

    if score >= threshold:
        return GateResult(passed=True, confidence=score, action=PROCEED,
                          skip_full_eval=False)
    if score >= ESCALATE_FLOOR:
        return GateResult(passed=False, confidence=score, action=ESCALATE,
                          skip_full_eval=False)
    return GateResult(passed=False, confidence=score, action=BLOCK_AND_REGENERATE,
                      skip_full_eval=True)


# ===========================================================================
# Layer 1: context evaluator
# ===========================================================================

@dataclass
class ContextVerdict:
    sufficient: bool
    missing_information: List[str]
    conflicting_statements: List[str]
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Antonym pairs for the lightweight contradiction scan. Deterministic and
# intentionally conservative: it flags a conflict only when both polarity words
# appear in different sentences that share an entity token.
_ANTONYMS = (
    ("deprecated", "supported"),
    ("increased", "decreased"),
    ("sufficient", "insufficient"),
    ("enabled", "disabled"),
    ("added", "removed"),
)


def _sentences(text: str) -> List[str]:
    parts = re.split(r"[.;\n]", text)
    return [p.strip() for p in parts if p.strip()]


def _detect_conflicts(context: str) -> List[str]:
    sents = _sentences(context)
    tokset = [set(_content_tokens(s)) for s in sents]
    conflicts: List[str] = []
    for w1, w2 in _ANTONYMS:
        idx1 = [i for i, s in enumerate(sents) if w1 in tokset[i]]
        idx2 = [i for i, s in enumerate(sents) if w2 in tokset[i]]
        for i in idx1:
            for j in idx2:
                if i == j:
                    continue
                shared = (tokset[i] - {w1}) & (tokset[j] - {w2})
                shared = {t for t in shared if _is_entity(t)}
                if shared:
                    conflicts.append(
                        f"'{sents[i]}' conflicts with '{sents[j]}' on {sorted(shared)}"
                    )
    return conflicts


def _claim_present(claim: str, context_l: str) -> bool:
    claim_tokens = _content_tokens(claim)
    if not claim_tokens:
        return True
    return all(t in context_l for t in claim_tokens)


def layer1_context_evaluator(
    query: str,
    context: str,
    required_claims: Optional[List[str]] = None,
) -> ContextVerdict:
    """Layer 1: did the agent possess the information it needed?

    Sufficient iff every required claim token-appears in the context. Each
    absent claim is listed in missing_information so the fix is scoped to the
    knowledge graph or retrieval pipeline, not the agent's reasoning (Ch7:
    "a failure here is not a reasoning failure").

    With no required_claims supplied, insufficiency cannot be detected, so the
    verdict defaults to sufficient at a high confidence.

    # TODO(production): swap for a Meta J1 reasoning-trace judge that emits a
    <think> justification and binary sufficient/not verdict (the chapter's context-sufficiency verdict shape),
    validated against domain-expert labels until agreement exceeds 90%.
    """
    claims = list(required_claims or [])
    context_l = context.lower()
    missing = [c for c in claims if not _claim_present(c, context_l)]
    conflicts = _detect_conflicts(context)
    sufficient = len(missing) == 0 and len(conflicts) == 0

    if claims:
        present = len(claims) - len(missing)
        confidence = round(present / len(claims), 2)
    else:
        confidence = 0.97

    return ContextVerdict(
        sufficient=sufficient,
        missing_information=missing,
        conflicting_statements=conflicts,
        confidence=confidence,
    )


# ===========================================================================
# Layer 2: cognitive fault isolator
# ===========================================================================

@dataclass
class CognitiveVerdict:
    failure_type: str                 # "KNOWLEDGE" | "REASONING"
    fault_location: Dict[str, Any]
    knowledge_index: float
    infogain_trace: List[float]
    low_infogain_steps: List[int]
    diagnosis: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def layer2_cognitive_fault_isolator(
    infogain_trace: List[float],
    knowledge_index: float,
    fault_node: Optional[Dict[str, Any]] = None,
    ki_threshold: float = 0.8,
    infogain_floor: float = 0.05,
    diagnosis: str = "",
) -> CognitiveVerdict:
    """Layer 2: knowledge failure or reasoning failure?

    Two mutually exclusive categories (Ch7):
      KNOWLEDGE failure: reasoning is coherent but operates on wrong facts.
        Detected by a Knowledge Index below ki_threshold.
      REASONING failure: the agent has the right facts but fails to connect
        them. Detected by near-zero / negative InfoGain steps.

    low_infogain_steps are the 1-based step indices where InfoGain fell below
    infogain_floor. The DevOps premature-closure trace [0.34, 0.29, 0.22, 0.03,
    -0.01, 0.19] yields steps [4, 5] at the default floor of 0.05 (Ch7 Example
    7-16 / 7-17).

    # TODO(production): swap for the J1 judge + MICRO-ACT DECOMPOSE pipeline
    that computes the Knowledge Index from atomic verified claims, and for the
    InfoGain estimator P(Answer | reasoning_up_to_step_i) over the trace.
    """
    if not 0.0 <= ki_threshold <= 1.0:
        raise ValueError(f"ki_threshold must be in [0, 1], got {ki_threshold}")
    low_infogain_steps = [
        i + 1 for i, v in enumerate(infogain_trace) if v < infogain_floor
    ]
    failure_type = "KNOWLEDGE" if knowledge_index < ki_threshold else "REASONING"
    return CognitiveVerdict(
        failure_type=failure_type,
        fault_location=dict(fault_node or {}),
        knowledge_index=knowledge_index,
        infogain_trace=list(infogain_trace),
        low_infogain_steps=low_infogain_steps,
        diagnosis=diagnosis,
    )


# ===========================================================================
# Layer 3: tool-integrated reasoning judge (TIR-Judge)
# ===========================================================================

@dataclass
class TIRReward:
    correctness: float
    format_compliance: float
    tool_accuracy: float
    composite: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def layer3_tir_judge(
    claim_value: Any,
    expected_value: Any,
    format_ok: bool = True,
    tool_ok: bool = True,
) -> TIRReward:
    """Layer 3: verify a quantitative claim by comparison against ground truth.

    Three-component reward (the chapter's tool-integrated-reasoning reward example). The composite is MULTIPLICATIVE,
    not additive: a perfectly formatted response with an incorrect answer
    scores zero, because a confidently wrong answer that looks well structured
    is more dangerous than an obviously malformed one.

    correctness = 1.0 iff claim_value == expected_value, else 0.0.

    # TODO(production): swap for a TIR-Judge CodeExecutor that generates a
    Cypher query against the KG, computes the expected value from the metrics
    subgraph, and returns the binary correctness signal.
    """
    correctness = 1.0 if claim_value == expected_value else 0.0
    format_compliance = 1.0 if format_ok else 0.0
    tool_accuracy = 1.0 if tool_ok else 0.0
    composite = correctness * format_compliance * tool_accuracy
    return TIRReward(
        correctness=correctness,
        format_compliance=format_compliance,
        tool_accuracy=tool_accuracy,
        composite=composite,
    )


# ===========================================================================
# The cascade: run the four layers, stop at the first failing layer
# ===========================================================================

def _target_nodes(fault_node: Optional[Dict[str, Any]]) -> List[str]:
    if fault_node and fault_node.get("node_id"):
        return [fault_node["node_id"]]
    return []


def run_cascade(execution: Dict[str, Any]) -> Dict[str, Any]:
    """Run Layer 0 -> 1 -> 2 -> 3, stopping at the first failing layer.

    `execution` keys (all read defensively):
      execution_id, query, answer, context_premise, required_claims,
      infogain_trace, knowledge_index, fault_node, claim_value, expected_value,
      format_ok, tool_ok, diagnosis.

    Returns a diagnostic report shaped like the chapter's diagnostic-report example:
      execution_id, overall_verdict ("PASS" | "FAILURE"), stopped_at_layer
      (0/1/2/3 or None), layer_1_context (when reached), layer_2_cognitive
      (when reached), recommended_intervention, target_nodes.

    Recommended-intervention mapping:
      Layer 0 hard block          -> BLOCK_AND_REGENERATE
      Layer 1 not sufficient      -> RETRIEVAL_FIX
      Layer 2 REASONING, <=2 low
        steps, KI > 0.8           -> PROMPT_REFINEMENT
      any other cognitive / L3
        failure                   -> FINE_TUNE
      all layers pass             -> NONE
    """
    execution_id = execution.get("execution_id", "unknown")
    report: Dict[str, Any] = {
        "execution_id": execution_id,
        "overall_verdict": "PASS",
        "stopped_at_layer": None,
        "recommended_intervention": NONE,
        "target_nodes": [],
    }

    query = execution.get("query", "")
    answer = execution.get("answer", "")
    premise = execution.get("context_premise", "")

    # -- Layer 0 -----------------------------------------------------------
    gate = layer0_hallucination_gate(query, answer, premise)
    report["layer_0_gate"] = gate.to_dict()
    if gate.skip_full_eval:
        report["overall_verdict"] = "FAILURE"
        report["stopped_at_layer"] = 0
        report["recommended_intervention"] = BLOCK_AND_REGENERATE
        report["target_nodes"] = []
        return report

    # -- Layer 1 -----------------------------------------------------------
    ctx = layer1_context_evaluator(
        query, premise, execution.get("required_claims"),
    )
    report["layer_1_context"] = {
        "sufficient": ctx.sufficient,
        "confidence": ctx.confidence,
        "missing_information": ctx.missing_information,
        "conflicting_statements": ctx.conflicting_statements,
    }
    if not ctx.sufficient:
        report["overall_verdict"] = "FAILURE"
        report["stopped_at_layer"] = 1
        report["recommended_intervention"] = RETRIEVAL_FIX
        report["target_nodes"] = []
        return report

    # -- Layer 2 -----------------------------------------------------------
    fault_node = execution.get("fault_node")
    ki = execution.get("knowledge_index", 1.0)
    cog = layer2_cognitive_fault_isolator(
        infogain_trace=execution.get("infogain_trace", []),
        knowledge_index=ki,
        fault_node=fault_node,
        diagnosis=execution.get("diagnosis", ""),
    )
    cognitive_fault = bool(cog.low_infogain_steps) or (ki < 0.8)
    if cognitive_fault:
        report["layer_2_cognitive"] = cog.to_dict()
        report["overall_verdict"] = "FAILURE"
        report["stopped_at_layer"] = 2
        report["target_nodes"] = _target_nodes(fault_node)
        if (cog.failure_type == "REASONING"
                and len(cog.low_infogain_steps) <= 2 and ki > 0.8):
            report["recommended_intervention"] = PROMPT_REFINEMENT
        else:
            report["recommended_intervention"] = FINE_TUNE
        return report

    # -- Layer 3 -----------------------------------------------------------
    reward = layer3_tir_judge(
        claim_value=execution.get("claim_value"),
        expected_value=execution.get("expected_value"),
        format_ok=execution.get("format_ok", True),
        tool_ok=execution.get("tool_ok", True),
    )
    report["layer_3_tir"] = reward.to_dict()
    if reward.composite == 0.0:
        report["overall_verdict"] = "FAILURE"
        report["stopped_at_layer"] = 3
        report["recommended_intervention"] = FINE_TUNE
        report["target_nodes"] = _target_nodes(fault_node)
        return report

    return report
