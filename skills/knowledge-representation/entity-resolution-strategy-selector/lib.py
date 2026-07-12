"""
Entity resolution strategy selection (evidence-based vs generalization-based
AI) plus a deterministic feature-scoring matcher, edge-type classification, and
edge-case detection. Distilled from Ch3 "Entity Resolution: The Foundation of
Agent Knowledge".

The chapter's central distinction:

  EVIDENCE-BASED resolution      examines specific features, applies domain
                                 matching rules, builds a case from concrete
                                 evidence. Deterministic, explainable,
                                 culturally robust, calibrated confidence.
  GENERALIZATION-BASED AI (LLM)  infers from statistical similarity learned in
                                 training. Nondeterministic, post-hoc
                                 rationalizations, breaks on non-Western names,
                                 confidence not tied to accuracy.

Evidence-based wins for identity / compliance / high-stakes / adversarial work
(channel-separation fraud, where variations are deliberately engineered to pass
fuzzy filters). Generalization-AI is acceptable for low-stakes fuzzy dedup with
abundant examples and no compliance need. Mixed profiles get a hybrid.

The matcher scores per-feature similarity (name, address, phone) and aggregates
to an explainable confidence with evidence metadata -- mirroring the chapter's
"89% because NAME 87%, ADDRESS 100%, PHONE 95%".

Pure Python, stdlib only. No ML model, no external service.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# Strategy selection: evidence-based vs generalization-based AI.
# ---------------------------------------------------------------------------

STRATEGIES = ("evidence_based", "generalization_ai")

FACTORS = ("high_stakes", "adversarial", "needs_explainability",
           "needs_determinism", "cultural_variation", "has_training_examples")

# How well each strategy serves each need, on a 0..3 ordinal scale distilled
# from the "Evidence-based resolution vs generalization-based AI" section.
# Evidence-based is strong exactly where the chapter says generalization fails:
# determinism, explainability, cultural robustness, adversarial resistance.
# Generalization-AI's only lever is abundant training examples for low-stakes
# fuzzy dedup.
STRATEGY_FACTOR_SCORES: Dict[str, Dict[str, int]] = {
    "evidence_based": {
        "high_stakes": 3, "adversarial": 3, "needs_explainability": 3,
        "needs_determinism": 3, "cultural_variation": 3,
        "has_training_examples": 0,
    },
    "generalization_ai": {
        "high_stakes": 0, "adversarial": 0, "needs_explainability": 0,
        "needs_determinism": 0, "cultural_variation": 0,
        "has_training_examples": 3,
    },
}


@dataclass
class StrategyProfile:
    """Caller-supplied resolution requirements, each a weight 0..3.

    high_stakes: identity / compliance / legal consequences on a wrong merge.
    adversarial: bad actors engineer variations to defeat matching
        (channel-separation fraud: same person as Bob Jones and Bob R. Smith II
        at the same address with different phone formatting).
    needs_explainability: every match must cite the evidence that established it.
    needs_determinism: same input must always produce the same output.
    cultural_variation: names span non-Western conventions (Arabic, Chinese,
        Russian) that statistical similarity mishandles.
    has_training_examples: abundant labeled pairs exist to learn from.
    """
    high_stakes: int = 0
    adversarial: int = 0
    needs_explainability: int = 0
    needs_determinism: int = 0
    cultural_variation: int = 0
    has_training_examples: int = 0

    def as_weights(self) -> Dict[str, int]:
        return {f: int(getattr(self, f)) for f in FACTORS}


def score_strategies(profile: StrategyProfile) -> List[Tuple[str, float]]:
    """Weighted dot-product of profile weights and per-strategy affinities.
    Returns [(strategy, score), ...] sorted descending.
    """
    weights = profile.as_weights()
    scored: List[Tuple[str, float]] = []
    for strat in STRATEGIES:
        aff = STRATEGY_FACTOR_SCORES[strat]
        total = float(sum(weights[f] * aff[f] for f in FACTORS))
        scored.append((strat, total))
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return scored


_RATIONALE = {
    "evidence_based": ("Feature-by-feature scoring with explicit domain rules: "
                       "deterministic, explainable (every match cites which "
                       "features drove it), culturally robust, and calibrated. "
                       "The right default for identity, compliance, high-stakes, "
                       "and adversarial channel-consolidation work."),
    "generalization_ai": ("LLM statistical similarity over learned patterns: "
                          "fast to stand up when labeled examples are abundant "
                          "and the task is low-stakes fuzzy dedup. Nondeterministic "
                          "and post-hoc; unsafe where a wrong merge has legal or "
                          "compliance consequences."),
    "hybrid": ("Neither axis dominates: use generalization-AI to cheaply propose "
               "candidate pairs (blocking) and evidence-based scoring to make the "
               "final, explainable, auditable merge decision. Record it as a "
               "conscious trade-off, not a non-decision."),
}


def recommend_strategy(profile: StrategyProfile) -> Dict[str, Any]:
    """Pick a resolution strategy and explain. Surfaces a hybrid when the top
    two scores are close and both non-trivial."""
    scored = score_strategies(profile)
    top_strat, top_score = scored[0]
    second_strat, second_score = scored[1]
    margin = top_score - second_score
    hybrid = top_score > 0 and second_score > 0 and margin <= max(1.0, 0.25 * top_score)
    recommended = "hybrid" if hybrid else top_strat
    rec = {
        "recommended": recommended,
        "scores": dict(scored),
        "rationale": _RATIONALE[recommended],
        "hybrid_recommended": hybrid,
    }
    if hybrid:
        rec["hybrid"] = f"{top_strat} + {second_strat}"
        rec["hybrid_note"] = (
            f"Top two scores are within {margin:.1f}; generalization-AI for "
            "candidate generation, evidence-based for the auditable final "
            "decision (Ch3 evidence-vs-generalization distinction)."
        )
    return rec


# ---------------------------------------------------------------------------
# Deterministic feature-scoring matcher. Mirrors the chapter's explainable
# "89% because NAME 87%, ADDRESS 100%, PHONE 95%".
# ---------------------------------------------------------------------------

_DEFAULT_FEATURE_WEIGHTS = {"name": 0.4, "address": 0.3, "phone": 0.3}

# Naming particles / honorifics stripped before comparing name cores so that
# culturally-varied forms of the same name align (al-Hajj, Abu, bin, Jr, II...).
_NAME_PARTICLES = {
    "al", "hajj", "abu", "bin", "ibn", "bint", "abd", "abdul",
    "jr", "sr", "ii", "iii", "iv", "dr", "mr", "mrs", "ms", "the",
    "von", "van", "de", "da", "del", "la", "le", "san",
}

# Generic street/locality tokens that should not, on their own, establish that
# two addresses reference the same location.
_ADDRESS_STOPWORDS = {
    "road", "rd", "street", "st", "avenue", "ave", "tower", "block",
    "unit", "apt", "suite", "floor", "singapore", "sng", "usa",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def _tokens(text: str) -> List[str]:
    return [t for t in re.sub(r"[^0-9a-z]+", " ", _norm(text)).split() if t]


def _digits(text: str) -> str:
    return re.sub(r"\D", "", str(text))


def _string_similarity(a: str, b: str) -> float:
    return round(SequenceMatcher(None, _norm(a), _norm(b)).ratio(), 4)


def _feature_similarity(feature: str, a: Any, b: Any) -> float:
    """Per-feature deterministic similarity in [0, 1]."""
    if feature == "phone":
        da, db = _digits(a), _digits(b)
        if not da or not db:
            return 0.0
        # Format-insensitive: compare digit strings (last 7-10 digits align).
        return round(SequenceMatcher(None, da, db).ratio(), 4)
    return _string_similarity(a, b)


def resolve_match(record_a: Dict[str, Any], record_b: Dict[str, Any],
                  feature_weights: Dict[str, float] | None = None) -> Dict[str, Any]:
    """Score two records feature-by-feature and aggregate to an explainable
    confidence with evidence metadata.

    Only features present (and non-empty) in BOTH records are scored; weights
    are renormalized over the features actually used. Returns the aggregate
    confidence, the per-feature evidence (which features drove the decision and
    their individual scores), and the resulting edge type.
    """
    weights = dict(feature_weights or _DEFAULT_FEATURE_WEIGHTS)
    used: List[str] = [
        f for f in weights
        if record_a.get(f) not in (None, "") and record_b.get(f) not in (None, "")
    ]
    if not used:
        return {
            "confidence": 0.0, "edge_type": "NO_MATCH",
            "features_used": [], "evidence": [],
        }
    total_w = sum(weights[f] for f in used) or 1.0
    evidence = []
    confidence = 0.0
    for f in used:
        score = _feature_similarity(f, record_a[f], record_b[f])
        w = weights[f] / total_w
        contribution = round(score * w, 4)
        confidence += contribution
        evidence.append({
            "feature": f,
            "score": score,
            "weight": round(w, 4),
            "contribution": contribution,
        })
    confidence = round(confidence, 4)
    # Evidence sorted by what drove the decision most (the chapter's "which
    # features drove the match").
    evidence.sort(key=lambda e: e["contribution"], reverse=True)
    return {
        "confidence": confidence,
        "edge_type": classify_edge(confidence)["edge_type"],
        "features_used": used,
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# Edge-type classification. Entity resolution builds graph edges (Ch3 "Entity
# resolution as graph building blocks"): RESOLVED (strong same-entity),
# POSSIBLY_RELATED (weaker connection), DISCLOSED (declared in source data).
# ---------------------------------------------------------------------------

RESOLVED_THRESHOLD = 0.85
POSSIBLY_RELATED_THRESHOLD = 0.5


def classify_edge(confidence: float, declared: bool = False) -> Dict[str, Any]:
    """Map a match confidence (or a declared relationship) to an edge type.

    declared=True always yields DISCLOSED (a known relationship from source
    data, not derived from feature scoring). Otherwise thresholds on confidence.
    """
    if declared:
        return {
            "edge_type": "DISCLOSED", "confidence": round(float(confidence), 4),
            "reason": "declared relationship present in source data",
        }
    c = float(confidence)
    if c >= RESOLVED_THRESHOLD:
        et, reason = "RESOLVED", "strong evidence records are the same entity"
    elif c >= POSSIBLY_RELATED_THRESHOLD:
        et, reason = "POSSIBLY_RELATED", "weaker evidence of a connection"
    else:
        et, reason = "NO_MATCH", "insufficient evidence to link"
    return {"edge_type": et, "confidence": round(c, 4), "reason": reason}


# ---------------------------------------------------------------------------
# Edge-case detection (Ch3 "Edge cases"). The three cases simple approaches
# miss, each requiring domain / cultural knowledge.
# ---------------------------------------------------------------------------

def _name_core(name: str) -> List[str]:
    return [t for t in _tokens(name) if t not in _NAME_PARTICLES and len(t) > 1]


def flag_edge_cases(record_a: Dict[str, Any],
                    record_b: Dict[str, Any]) -> List[Dict[str, str]]:
    """Detect the three entity-resolution edge cases that break naive matching.

    (a) very different strings, same entity -- honorifics / naming conventions
        (al-Hajj Abdullah Qardash vs Abu Abdullah Qardash bin Amir).
    (b) nearly identical strings, different entity -- a single distinguishing
        token (John R Smith vs John E Smith); caution, do not merge.
    (c) different address strings, same physical location -- component overlap
        under different formatting conventions.
    """
    warnings: List[Dict[str, str]] = []
    name_a, name_b = record_a.get("name", ""), record_b.get("name", "")
    addr_a, addr_b = record_a.get("address", ""), record_b.get("address", "")

    # (a) different strings, same entity.
    if name_a and name_b:
        raw = _string_similarity(name_a, name_b)
        core_a, core_b = set(_name_core(name_a)), set(_name_core(name_b))
        shared = core_a & core_b
        # Not a confident full-string match, yet the cores align on >=2
        # components once honorifics/particles are stripped.
        if raw < RESOLVED_THRESHOLD and len(shared) >= 2:
            warnings.append({
                "case": "different_strings_same_entity",
                "warning": (f"Names are not a confident full-string match "
                            f"(similarity {raw:.2f}) but share core components "
                            f"{sorted(shared)} once honorifics/particles are "
                            "stripped -- likely the same entity."),
                "action": "review_for_merge",
            })

    # (b) nearly identical strings, different entity.
    if name_a and name_b:
        raw = _string_similarity(name_a, name_b)
        ta, tb = _tokens(name_a), _tokens(name_b)
        initials_a = {t for t in ta if len(t) == 1}
        initials_b = {t for t in tb if len(t) == 1}
        distinguishing_initial = bool(initials_a ^ initials_b) and (initials_a and initials_b)
        if raw >= 0.8 and set(ta) != set(tb) and distinguishing_initial:
            warnings.append({
                "case": "near_identical_different_entity",
                "warning": (f"Names are nearly identical (similarity {raw:.2f}) "
                            "but differ by a distinguishing initial "
                            f"({sorted(initials_a ^ initials_b)}) -- potentially "
                            "distinct people (e.g. father/son)."),
                "action": "do_not_merge_without_evidence",
            })

    # (c) different address strings, same location.
    if addr_a and addr_b:
        raw = _string_similarity(addr_a, addr_b)
        ta = [t for t in _tokens(addr_a) if t not in _ADDRESS_STOPWORDS]
        tb = [t for t in _tokens(addr_b) if t not in _ADDRESS_STOPWORDS]
        shared = set(ta) & set(tb)
        shared_numbers = {t for t in shared if t.isdigit()}
        shared_names = {t for t in shared if not t.isdigit()}
        if raw < 0.6 and shared_numbers and shared_names:
            warnings.append({
                "case": "different_address_same_location",
                "warning": (f"Addresses differ as strings (similarity {raw:.2f}) "
                            f"but share numeric components {sorted(shared_numbers)} "
                            f"and locality tokens {sorted(shared_names)} -- likely "
                            "the same location under different formatting."),
                "action": "normalize_and_review",
            })

    return warnings
