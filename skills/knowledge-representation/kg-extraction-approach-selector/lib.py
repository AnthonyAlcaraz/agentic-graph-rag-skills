"""
Knowledge-graph extraction-approach selection, distilled from Ch3
"Extraction Approaches for Heterogeneous Sources".

Agents draw knowledge from diverse sources, and each source shape calls for a
different extraction strategy. The chapter names four:

  structured_db     Map an existing relational/NoSQL schema into graph nodes
                    and edges (materialization / virtual views / hybrid).
                    Deterministic, high-precision -- only for already-structured
                    sources.
  llm_extraction    Prompt an LLM for subject-predicate-object triples from free
                    text, validated against a domain ontology. Flexible, handles
                    any unstructured text, but non-deterministic; needs validation
                    and human-in-the-loop on low-confidence output.
  itext2kg          Incremental, topic-independent construction. Extracts entities
                    and relations section-by-section and disambiguates against the
                    prior set, so a growing corpus is extended WITHOUT re-processing
                    everything. No domain-specific schema required.
  rakg              Document-level Retrieval-Augmented KG construction. Gathers all
                    text segments where an entity appears plus related subgraphs
                    BEFORE generating relations, giving whole-document context and
                    filtering hallucinated relationships (reported 96% accuracy /
                    88% entity coverage / 95% relationship fidelity).

Each approach is scored across five features weighted by a SOURCE PROFILE. The
chapter's rule: the source shape and the reasoning need pick the approach, not
the other way round.

Pure Python, stdlib only. No LLM or graph database required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


APPROACHES = ("structured_db", "llm_extraction", "itext2kg", "rakg")

FEATURES = ("handles_unstructured", "incremental_friendly",
            "document_level_context", "determinism", "setup_cost")

# Per-approach scores per feature, on a 0..3 ordinal scale distilled from the
# "Extraction Approaches" section. Higher == stronger on that axis. Note
# `setup_cost` is scored as LOW-setup-cost (3 == minimal setup, 0 == heavy),
# so the weighted dot-product keeps the higher-is-better convention.
#   handles_unstructured    can it extract from free text at all
#   incremental_friendly    can it extend a growing corpus without full rebuild
#   document_level_context  does it reason across a whole document / all mentions
#   determinism             deterministic + high-precision (vs LLM variance)
#   setup_cost              simplicity to stand up (higher == less setup)
APPROACH_FEATURE_SCORES: Dict[str, Dict[str, int]] = {
    "structured_db": {
        "handles_unstructured": 0, "incremental_friendly": 2,
        "document_level_context": 1, "determinism": 3, "setup_cost": 1,
    },
    "llm_extraction": {
        "handles_unstructured": 3, "incremental_friendly": 1,
        "document_level_context": 1, "determinism": 1, "setup_cost": 3,
    },
    "itext2kg": {
        "handles_unstructured": 3, "incremental_friendly": 3,
        "document_level_context": 1, "determinism": 1, "setup_cost": 2,
    },
    "rakg": {
        "handles_unstructured": 3, "incremental_friendly": 1,
        "document_level_context": 3, "determinism": 2, "setup_cost": 1,
    },
}


@dataclass
class Profile:
    """Caller-supplied source profile that selects an extraction approach.

    source_type: "structured" (relational/NoSQL with a schema), "unstructured"
        (free text / documents), or "mixed".
    incremental: the corpus grows over time and re-extracting everything on each
        update is too expensive.
    document_context_needed: relations need cross-sentence / whole-document
        context (an entity's meaning is spread across many mentions).
    schema_stability: 0..3, how stable and known the target schema is. A stable
        schema reinforces deterministic extraction; an evolving one favors the
        schema-free LLM frameworks.
    determinism_need: 0..3, how much precision / reproducibility matters vs
        flexibility.
    volume: document count (informational; drives incremental_cost).
    """
    source_type: str = "unstructured"
    incremental: bool = False
    document_context_needed: bool = False
    schema_stability: int = 0
    determinism_need: int = 0
    volume: int = 0

    def weights(self) -> Dict[str, int]:
        unstructured = self.source_type in ("unstructured", "mixed")
        # A stable, known schema adds one notch of determinism preference.
        determinism = min(3, int(self.determinism_need)
                          + (1 if int(self.schema_stability) >= 2 else 0))
        return {
            "handles_unstructured": 3 if unstructured else 0,
            "incremental_friendly": 3 if self.incremental else 0,
            "document_level_context": 3 if self.document_context_needed else 0,
            "determinism": determinism,
            # Baseline preference for the simplest approach breaks otherwise-tied
            # one-shot unstructured cases toward plain LLM extraction.
            "setup_cost": 1,
        }


def score_approaches(profile: Profile) -> List[Tuple[str, float]]:
    """Weighted dot-product of profile weights and per-approach feature scores.
    Returns [(approach, score), ...] sorted descending.
    """
    weights = profile.weights()
    scored: List[Tuple[str, float]] = []
    for approach in APPROACHES:
        feats = APPROACH_FEATURE_SCORES[approach]
        total = float(sum(weights[f] * feats[f] for f in FEATURES))
        scored.append((approach, total))
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return scored


def recommend_approach(profile: Profile) -> Dict[str, Any]:
    """Pick an extraction approach and explain.

    A structured source is a categorical fact, not a preference: you materialize
    an existing schema, you do not LLM-extract triples from a relational table.
    So `source_type == "structured"` hard-routes to structured_db regardless of
    the weighted scores (which still ride along in `ranked` for transparency).
    Everything else is decided by the scoring:
      unstructured + incremental      -> itext2kg  (extend, don't re-extract)
      unstructured + doc-context      -> rakg      (whole-document grounding)
      unstructured, one-shot          -> llm_extraction (simplest that fits)
    """
    ranked = score_approaches(profile)
    if profile.source_type == "structured":
        recommended = "structured_db"
    else:
        recommended = ranked[0][0]
    return {
        "recommended": recommended,
        "ranked": ranked,
        "rationale": _RATIONALE[recommended],
        "source_type": profile.source_type,
    }


_RATIONALE = {
    "structured_db": ("Source already has a schema: materialize it (batch or CDC "
                      "stream) or expose virtual graph views. Deterministic and "
                      "high-precision; no LLM variance to validate."),
    "llm_extraction": ("Prompt an LLM for ontology-constrained triples from free "
                       "text. Simplest to stand up; flexible across topics. "
                       "Non-deterministic, so validate against the ontology and "
                       "route low-confidence extractions to human review."),
    "itext2kg": ("Incremental, schema-free construction: extract per section and "
                 "disambiguate against the prior entity set, so a growing corpus "
                 "is extended without re-processing what is already ingested."),
    "rakg": ("Document-level retrieval-augmented extraction: gather every mention "
             "of an entity plus related subgraphs before generating relations. "
             "Whole-document context plus hallucination filtering (high "
             "relationship fidelity), at the cost of retrieval infrastructure."),
}


# ---------------------------------------------------------------------------
# Incremental cost. The chapter's iText2KG win is concrete: an incremental
# framework processes only the NEW documents on an update, while a batch /
# full-rebuild approach re-processes the entire corpus every time.
# ---------------------------------------------------------------------------

INCREMENTAL_APPROACHES = ("itext2kg",)


def incremental_cost(new_docs: int, total_docs: int,
                     approach: str) -> Dict[str, Any]:
    """Documents each approach re-processes when `new_docs` are added to a corpus
    that will then hold `total_docs`.

    itext2kg processes only the new documents; a full-rebuild approach
    (structured_db batch, llm_extraction, rakg) re-processes all total_docs.
    Returns the doc counts each pays, plus the wasted re-extraction and the
    savings versus a full rebuild.
    """
    if new_docs < 0 or total_docs < new_docs:
        raise ValueError("require 0 <= new_docs <= total_docs")
    incremental = approach in INCREMENTAL_APPROACHES
    docs_processed = new_docs if incremental else total_docs
    return {
        "approach": approach,
        "incremental": incremental,
        "new_docs": new_docs,
        "total_docs": total_docs,
        "docs_processed": docs_processed,
        "docs_reprocessed": docs_processed - new_docs,   # wasted re-extraction
        "savings_vs_rebuild": total_docs - docs_processed,
    }
