"""
Three-Graph Architecture router (Ch3 "The Three-Graph Architecture for Agent
Knowledge").

Routes an incoming record/fact into one of three graphs by ORIGIN, CERTAINTY,
and SEMANTIC ROLE:

  domain  -> trusted, curated, entity-resolved single source of truth
             (structured sources, stable IDs, definitive relationships)
  lexical -> original unstructured text preserved verbatim, with provenance
             (Document/Chunk nodes, immutable, the "retrieval" in RAG)
  subject -> LLM-extracted entities/facts kept SEPARATE from domain until
             entity resolution links them (extraction artifacts, explicit
             uncertainty, confidence scores + model version)

The critical operation that makes the architecture work is entity resolution:
a Subject entity links to a Domain entity via CORRESPONDS_TO only when a
similarity score exceeds a confidence threshold. This module models the router,
the labeling discipline (:Product:Domain vs :Product:Subject), and the
CORRESPONDS_TO linkage gate.

Pure Python, stdlib only. The similarity function is a deterministic stub at a
documented seam where a real embedding/Jaro-Winkler matcher swaps in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple


DOMAIN, LEXICAL, SUBJECT = "domain", "lexical", "subject"
GRAPHS = (DOMAIN, LEXICAL, SUBJECT)

# Default CORRESPONDS_TO threshold. Ch3 entity-linking section recommends 0.85
# as the default (0.95 high-stakes, 0.75 exploratory).
DEFAULT_THRESHOLD = 0.85


@dataclass
class Record:
    """An incoming piece of knowledge to route.

    origin: where it came from. Recognized origins:
        structured: database/CSV row, API response from a system of record.
        raw_text:   a document chunk / review / report passage (verbatim).
        extraction: an entity or fact an LLM pulled out of raw text.
    entity_resolved: True only if this record came through entity resolution
        with a stable id (forces domain).
    has_provenance: True if the record links back to a source document.
    confidence: extraction confidence (only meaningful for extraction origin).
    """
    payload: Dict[str, Any]
    origin: str
    entity_resolved: bool = False
    has_provenance: bool = False
    confidence: Optional[float] = None


def route(record: Record) -> Dict[str, Any]:
    """Decide which graph a record belongs in, and why.

    Returns {graph, label_suffix, reasons[], requires_resolution}.
    Routing failures (contradictory signals) raise ValueError so the caller
    cannot silently contaminate the domain graph.
    """
    reasons: List[str] = []
    o = record.origin

    if o == "structured":
        # Structured + entity-resolved is the canonical domain case.
        reasons.append("structured origin: candidate for trusted domain graph")
        if not record.entity_resolved:
            reasons.append(
                "WARNING: structured but not entity-resolved -- run entity "
                "resolution before treating as domain ground truth"
            )
        return {
            "graph": DOMAIN,
            "label_suffix": "Domain",
            "reasons": reasons,
            "requires_resolution": not record.entity_resolved,
        }

    if o == "raw_text":
        reasons.append("raw_text origin: verbatim source -> lexical graph")
        if not record.has_provenance:
            raise ValueError(
                "raw_text record has no provenance link; lexical graph requires "
                "every chunk to link back to its source document (Ch3 lexical "
                "key characteristic: complete provenance)"
            )
        reasons.append("provenance present: chunk links to source document")
        return {
            "graph": LEXICAL,
            "label_suffix": "Lexical",
            "reasons": reasons,
            "requires_resolution": False,
        }

    if o == "extraction":
        reasons.append("extraction origin: LLM artifact -> subject graph, kept "
                       "separate from domain until entity resolution")
        if record.confidence is None:
            raise ValueError(
                "extraction record has no confidence score; subject graph "
                "requires extraction metadata (Ch3 subject key characteristic: "
                "uncertainty acknowledged explicitly)"
            )
        if record.entity_resolved:
            raise ValueError(
                "extraction record marked entity_resolved=True cannot be routed "
                "directly to domain; it must enter the subject graph and link "
                "via CORRESPONDS_TO (Ch3: keep extractions separate from domain)"
            )
        return {
            "graph": SUBJECT,
            "label_suffix": "Subject",
            "reasons": reasons,
            "requires_resolution": True,
        }

    raise ValueError(f"unknown origin '{o}'; expected one of "
                     "structured / raw_text / extraction")


# ---------------------------------------------------------------------------
# Entity resolution / CORRESPONDS_TO linkage gate.
# ---------------------------------------------------------------------------

def _string_similarity(a: str, b: str) -> float:
    """Deterministic similarity stub.

    TODO: swap for production matcher -- embedding cosine similarity or
    Jaro-Winkler distance (Ch3 entity-linking section names Jaro-Winkler for
    value-similarity matching). SequenceMatcher keeps this dependency-free.
    """
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


@dataclass
class Correspondence:
    subject_id: str
    domain_id: str
    similarity: float
    linked: bool
    threshold: float


def link_subject_to_domain(
    subject_name: str,
    domain_candidates: Dict[str, str],
    threshold: float = DEFAULT_THRESHOLD,
    sim_fn=None,
) -> Optional[Correspondence]:
    """Find the best domain candidate for an extracted subject entity and
    create a CORRESPONDS_TO link only if similarity exceeds the threshold.

    domain_candidates: {domain_id: canonical_name}
    Returns the best Correspondence (linked True/False) or None if no candidates.
    """
    sim_fn = sim_fn or _string_similarity
    if not domain_candidates:
        return None
    best_id, best_sim = None, -1.0
    for did, dname in domain_candidates.items():
        s = sim_fn(subject_name, dname)
        if s > best_sim:
            best_id, best_sim = did, s
    return Correspondence(
        subject_id=subject_name,
        domain_id=best_id,
        similarity=best_sim,
        linked=best_sim >= threshold,
        threshold=threshold,
    )


def cross_graph_query_path(start_graph: str, target_graph: str) -> List[str]:
    """Return the traversal path between graphs for a cross-graph query.

    The canonical path (Ch3 "Why this architecture matters"): start at the
    domain graph (official entities), traverse CORRESPONDS_TO to the subject
    graph (extracted facts), follow EXTRACTED_FROM to the lexical graph
    (original text). Returns the edge-type sequence.
    """
    order = {DOMAIN: 0, SUBJECT: 1, LEXICAL: 2}
    edge_by_step = {
        (DOMAIN, SUBJECT): "CORRESPONDS_TO",
        (SUBJECT, LEXICAL): "EXTRACTED_FROM",
        (SUBJECT, DOMAIN): "CORRESPONDS_TO",
        (LEXICAL, SUBJECT): "EXTRACTED_FROM",
    }
    if start_graph not in order or target_graph not in order:
        raise ValueError("graphs must be one of domain/subject/lexical")
    if start_graph == target_graph:
        return []
    path: List[str] = []
    cur = order[start_graph]
    end = order[target_graph]
    step = 1 if end > cur else -1
    rev = {v: k for k, v in order.items()}
    while cur != end:
        nxt = cur + step
        path.append(edge_by_step[(rev[cur], rev[nxt])])
        cur = nxt
    return path
