"""
Letta 8-failure-modes diagnostic for agentic memory.

Static analyzer over a memory-architecture snapshot. Returns a report
listing each of the 8 failure modes with status / severity / evidence /
recommended fix.

The snapshot input shape is documented in `MemorySnapshot` below. It is
intentionally loose — any memory implementation can populate the fields
relevant to it; unknown fields are left None and the corresponding
failure modes report status="unknown" rather than false-positive.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Snapshot input shape — caller populates what they have
# ---------------------------------------------------------------------------

@dataclass
class MemorySnapshot:
    # Core / recall / archival sizes (e.g. from hierarchical-memory)
    core_size: Optional[int] = None
    core_limit: Optional[int] = None
    core_durable_count: Optional[int] = None
    core_short_lived_count: Optional[int] = None
    recall_size: Optional[int] = None
    archival_size: Optional[int] = None
    archival_durable_count: Optional[int] = None
    # Graph-shape signals
    node_count: Optional[int] = None
    edge_count: Optional[int] = None
    disconnected_components: Optional[int] = None
    avg_degree: Optional[float] = None
    # Temporal signals
    uses_bi_temporal_edges: Optional[bool] = None
    facts_without_created_at: Optional[int] = None
    facts_without_invalidation_reason_when_invalidated: Optional[int] = None
    # Retrieval / indexing signals
    retrieval_method: Optional[str] = None       # 'linear-scan' / 'bm25' / 'vector' / 'hybrid'
    retrieval_complexity_class: Optional[str] = None  # 'O(1)' / 'O(log n)' / 'O(n)'
    has_query_log: Optional[bool] = None
    # Extraction / ingestion signals
    extract_fn_present: Optional[bool] = None
    # Architecture / size stress
    size_stress_test_passed: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemorySnapshot":
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})


# ---------------------------------------------------------------------------
# Failure-mode entries
# ---------------------------------------------------------------------------

@dataclass
class FailureMode:
    name: str
    status: str           # 'ok' / 'warning' / 'present' / 'unknown'
    severity: int         # 0 (ok) / 1 (warning) / 2 (present-degraded) / 3 (present-critical)
    evidence: str
    fix: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiagnosticReport:
    modes: List[FailureMode] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"modes": [m.to_dict() for m in self.modes]}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DiagnosticReport":
        return cls(modes=[FailureMode(**m) for m in d["modes"]])


# ---------------------------------------------------------------------------
# Diagnostic logic
# ---------------------------------------------------------------------------

def _check_no_retrieval_when_available(s: MemorySnapshot) -> FailureMode:
    if s.has_query_log is None and s.recall_size is None:
        return FailureMode(
            name="no-retrieval-when-available",
            status="unknown", severity=0,
            evidence="snapshot does not include has_query_log or recall_size",
            fix="instrument the memory layer to log every query and recall access",
        )
    if s.recall_size == 0 and (s.archival_size or 0) > 5:
        return FailureMode(
            name="no-retrieval-when-available",
            status="present", severity=2,
            evidence=f"recall is empty but archival has {s.archival_size} entries — interaction history is being discarded",
            fix="wire up `process_interaction` to append to recall on every turn; verify with `mem.recall_size` > 0 after activity",
        )
    return FailureMode(
        name="no-retrieval-when-available",
        status="ok", severity=0,
        evidence=f"recall_size={s.recall_size}, has_query_log={s.has_query_log}",
        fix="(none required)",
    )


def _check_hierarchy_collapse(s: MemorySnapshot) -> FailureMode:
    if s.core_size is None or s.core_durable_count is None:
        return FailureMode(
            name="hierarchy-collapse",
            status="unknown", severity=0,
            evidence="snapshot missing core_size / core_durable_count — pass these from hierarchical-memory.diagnostics()",
            fix="invoke hierarchical-memory diagnostics and forward to this skill",
        )
    if s.core_size >= 5:
        short_ratio = (s.core_short_lived_count or 0) / max(1, s.core_size)
        if short_ratio > 0.5:
            return FailureMode(
                name="hierarchy-collapse",
                status="present", severity=2,
                evidence=f"core composition: {s.core_short_lived_count}/{s.core_size} short-lived ({short_ratio*100:.0f}%)",
                fix="tighten the durability classifier in `extract_fn`; mark only stable user-attributes / production-config as DURABLE",
            )
    if (s.archival_durable_count or 0) > (s.core_durable_count or 0) \
       and s.core_durable_count < (s.core_limit or 1) // 2:
        return FailureMode(
            name="hierarchy-collapse",
            status="present", severity=3,
            evidence=f"archival has {s.archival_durable_count} durable vs core's {s.core_durable_count} — durable facts being evicted",
            fix="raise DURABILITY_PROTECTION_FACTOR; or audit which durable facts are scoring low and why",
        )
    return FailureMode(
        name="hierarchy-collapse",
        status="ok", severity=0,
        evidence=f"core durable/short = {s.core_durable_count}/{s.core_short_lived_count}",
        fix="(none required)",
    )


def _check_in_conversation_misses(s: MemorySnapshot) -> FailureMode:
    if s.recall_size is None or s.core_size is None:
        return FailureMode(
            name="in-conversation-misses",
            status="unknown", severity=0,
            evidence="snapshot missing recall_size / core_size",
            fix="instrument hierarchical-memory and forward sizes",
        )
    if s.extract_fn_present is False:
        return FailureMode(
            name="in-conversation-misses",
            status="present", severity=3,
            evidence="extract_fn not wired — interactions logged but no facts promoted",
            fix="pass an extract_fn to process_interaction; use default_extract_fn as a starting point",
        )
    if s.recall_size > 5 and s.core_size == 0:
        return FailureMode(
            name="in-conversation-misses",
            status="present", severity=3,
            evidence=f"recall={s.recall_size} interactions, core empty — facts not promoting",
            fix="check extract_fn return values; ensure it returns (content, durability) tuples",
        )
    return FailureMode(
        name="in-conversation-misses",
        status="ok", severity=0,
        evidence=f"recall_size={s.recall_size}, core_size={s.core_size}, extract_fn_present={s.extract_fn_present}",
        fix="(none required)",
    )


def _check_volume_degradation(s: MemorySnapshot) -> FailureMode:
    if s.retrieval_complexity_class is None and s.retrieval_method is None:
        return FailureMode(
            name="volume-degradation",
            status="unknown", severity=0,
            evidence="snapshot missing retrieval_method / retrieval_complexity_class",
            fix="declare the retrieval method and its complexity class in the snapshot",
        )
    if s.retrieval_method == "linear-scan" or s.retrieval_complexity_class == "O(n)":
        return FailureMode(
            name="volume-degradation",
            status="present", severity=2,
            evidence=f"retrieval is {s.retrieval_method or s.retrieval_complexity_class} — does not scale past ~1k entries",
            fix="add an index: BM25 for text, ANN for embeddings, or both (hybrid). Production target: O(log n).",
        )
    return FailureMode(
        name="volume-degradation",
        status="ok", severity=0,
        evidence=f"retrieval={s.retrieval_method}, complexity={s.retrieval_complexity_class}",
        fix="(none required)",
    )


def _check_silent_overwrite(s: MemorySnapshot) -> FailureMode:
    if s.uses_bi_temporal_edges is None:
        return FailureMode(
            name="silent-overwrite",
            status="unknown", severity=0,
            evidence="snapshot missing uses_bi_temporal_edges flag",
            fix="declare whether bi-temporal-edge primitive is integrated for mutable facts",
        )
    if not s.uses_bi_temporal_edges:
        return FailureMode(
            name="silent-overwrite",
            status="present", severity=3,
            evidence="bi-temporal-edge primitive not integrated — facts overwrite without preserving history",
            fix="integrate `bi-temporal-edge` for any relationship that can change over time (configs, ownership, status, etc.)",
        )
    if (s.facts_without_invalidation_reason_when_invalidated or 0) > 0:
        return FailureMode(
            name="silent-overwrite",
            status="warning", severity=1,
            evidence=f"{s.facts_without_invalidation_reason_when_invalidated} invalidated facts have no reason",
            fix="enforce non-empty invalidation reason at the lib boundary (already enforced by bi-temporal-edge.lib.invalidate)",
        )
    return FailureMode(
        name="silent-overwrite",
        status="ok", severity=0,
        evidence="bi-temporal edges in use with full reason tracking",
        fix="(none required)",
    )


def _check_cross_reference_failure(s: MemorySnapshot) -> FailureMode:
    if s.node_count is None or s.avg_degree is None:
        return FailureMode(
            name="cross-reference-failure",
            status="unknown", severity=0,
            evidence="snapshot missing graph metrics",
            fix="compute node_count / edge_count / avg_degree / disconnected_components and forward",
        )
    if s.node_count == 0:
        return FailureMode(
            name="cross-reference-failure",
            status="warning", severity=1,
            evidence="graph is empty",
            fix="(populate graph)",
        )
    if s.avg_degree < 1.0:
        return FailureMode(
            name="cross-reference-failure",
            status="present", severity=2,
            evidence=f"avg_degree={s.avg_degree:.2f} — nodes are mostly isolated",
            fix="run graphiti-incremental-update with co-occurrence edges; or add explicit edge-extraction rules",
        )
    if s.disconnected_components is not None and s.disconnected_components > s.node_count / 10:
        return FailureMode(
            name="cross-reference-failure",
            status="warning", severity=1,
            evidence=f"{s.disconnected_components} disconnected components in {s.node_count}-node graph",
            fix="entity resolution may be too strict; review fuzzy_match threshold",
        )
    return FailureMode(
        name="cross-reference-failure",
        status="ok", severity=0,
        evidence=f"avg_degree={s.avg_degree:.2f}, components={s.disconnected_components}",
        fix="(none required)",
    )


def _check_temporal_blur(s: MemorySnapshot) -> FailureMode:
    if s.facts_without_created_at is None:
        return FailureMode(
            name="temporal-blur",
            status="unknown", severity=0,
            evidence="snapshot missing facts_without_created_at",
            fix="audit facts and count those lacking created_at timestamp",
        )
    if s.facts_without_created_at > 0:
        return FailureMode(
            name="temporal-blur",
            status="present", severity=2,
            evidence=f"{s.facts_without_created_at} facts have no created_at timestamp",
            fix="enforce created_at at the lib boundary; backfill from ingestion log if possible",
        )
    return FailureMode(
        name="temporal-blur",
        status="ok", severity=0,
        evidence="all facts have created_at",
        fix="(none required)",
    )


def _check_threshold_collapse(s: MemorySnapshot) -> FailureMode:
    if s.size_stress_test_passed is None:
        return FailureMode(
            name="threshold-collapse",
            status="unknown", severity=0,
            evidence="snapshot missing size_stress_test_passed",
            fix="run a 10x-scale scenario and report whether retrieval accuracy + latency held",
        )
    if not s.size_stress_test_passed:
        return FailureMode(
            name="threshold-collapse",
            status="present", severity=3,
            evidence="size stress test failed at 10x scale",
            fix="add indexes (volume-degradation fix) + hierarchical memory (hierarchy-collapse fix) — these two compose to defer threshold-collapse",
        )
    return FailureMode(
        name="threshold-collapse",
        status="ok", severity=0,
        evidence="size stress test passed",
        fix="(none required)",
    )


CHECKS = [
    _check_no_retrieval_when_available,
    _check_hierarchy_collapse,
    _check_in_conversation_misses,
    _check_volume_degradation,
    _check_silent_overwrite,
    _check_cross_reference_failure,
    _check_temporal_blur,
    _check_threshold_collapse,
]


def diagnose(snapshot: MemorySnapshot) -> DiagnosticReport:
    return DiagnosticReport(modes=[c(snapshot) for c in CHECKS])


def total_score(report: DiagnosticReport) -> int:
    return sum(m.severity for m in report.modes)


def format_text(report: DiagnosticReport) -> str:
    lines = ["=" * 70, "Letta 8-Failure-Modes Diagnostic Report", "=" * 70]
    for m in report.modes:
        status_marker = {"ok": "[OK]", "warning": "[WARN]", "present": "[FAIL]", "unknown": "[?]"}[m.status]
        lines.append(f"\n{status_marker} {m.name} (severity {m.severity}/3)")
        lines.append(f"  evidence: {m.evidence}")
        if m.status != "ok":
            lines.append(f"  fix: {m.fix}")
    lines.append("")
    lines.append("=" * 70)
    s = total_score(report)
    # Bands match SKILL.md Process Step 4: 0 = production-ready,
    # >=10 = ship at risk, >=18 = do not ship. The 1-9 band is below the
    # ship-at-risk threshold (minor issues to review, not yet at-risk).
    verdict = "production-ready" if s == 0 else \
              ("minor issues — review before ship" if s < 10 else
               ("ship at risk" if s < 18 else "do not ship"))
    lines.append(f"Total severity: {s}/24  ({verdict})")
    lines.append("=" * 70)
    return "\n".join(lines)


def format_json(report: DiagnosticReport) -> str:
    out = report.to_dict()
    out["total_score"] = total_score(report)
    return json.dumps(out, indent=2)
