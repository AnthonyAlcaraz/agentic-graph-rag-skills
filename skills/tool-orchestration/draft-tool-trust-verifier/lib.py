"""
DRAFT tool-trust verifier — learn what a tool actually does, not what it claims.

Distilled from Agentic GraphRAG (O'Reilly), Chapter 6 — Tool Orchestration
("The Trust Problem: When Tools Game the System" / "Verification-based trust" /
"DRAFT: Learning what tools actually do").

Tool providers optimize descriptions for DISCOVERY, not accuracy — "most
effective solution", "trusted by Fortune 500", "industry-leading". When every
tool claims to be the best, keyword-gamed descriptions defeat retrieval. The
chapter's answer is verification-based trust plus DRAFT (Documentation
Refinement through Automated Feedback and Testing, from Baidu's AI Search
Paradigm): don't trust provider descriptions, discover what tools actually do
through systematic experimentation.

Two trust mechanisms:
  1. Structured, verifiable capabilities — a tool declares enumerable functions
     with input/output types that can be TESTED, instead of free-text claims.
  2. Performance-based trust scores — every tool starts neutral; successes
     raise trust, failures / high latency / degradations lower it.

The DRAFT loop has three iterative phases, mirroring how a developer learns a
new API:
  1. Experience Gathering — an explorer probes tool boundaries, seeks edge
     cases, maps failure modes, and enforces diversity to avoid redundant tests.
  2. Learning from Experience — analyze the GAP between documentation and
     reality (claims "any text input" but fails on Unicode; undocumented
     payload-size latency).
  3. Documentation Rewriting — generate an AI-optimized spec reflecting the
     discovered reality (parameter types, ranges, error conditions, real
     performance), iterating until the doc converges with actual behavior.

STDLIB ONLY. The "tool under test" is simulated from declarative behavior rules
so the loop runs with zero external dependencies. In production the behavior is
the real tool and the explorer issues real calls.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# Marketing / unverifiable phrases that signal a gamed description (chapter:
# "Most effective solution", "Trusted by Fortune 500", "Industry-leading").
_MARKETING_RE = re.compile(
    r"\b(most effective|industry[- ]leading|revolutionary|best[- ]in[- ]class|"
    r"unparalleled|world[- ]class|cutting[- ]edge|trusted by (the )?fortune|"
    r"ai[- ]powered|breakthrough|state[- ]of[- ]the[- ]art|blazing[- ]?fast)\b",
    re.IGNORECASE,
)


def load_tool_under_test(path: str | Path) -> dict:
    """
    Load a tool spec with its CLAIMED documentation and a declarative behavior
    model (used to simulate the real tool for the explorer).
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------
# Mechanism 1 — structured, verifiable capabilities vs free-text claims
# ----------------------------------------------------------------------------

def verify_claims(tool: dict) -> dict:
    """
    Flag free-text marketing claims and confirm the tool declares STRUCTURED,
    testable capabilities (name + input/output types) instead. The chapter:
    a tool does not get to claim it "analyzes sentiment with unparalleled
    accuracy"; it declares the capability `sentiment_analysis` with specific
    input and output types.
    """
    description = tool.get("claimed_description", "")
    marketing_hits = sorted({m.group(0).lower() for m in _MARKETING_RE.finditer(description)})
    capabilities = tool.get("declared_capabilities", [])
    structured = [
        c for c in capabilities
        if c.get("name") and c.get("input_types") and c.get("output_types")
    ]
    return {
        "tool": tool.get("name"),
        "marketing_phrases": marketing_hits,
        "declared_capabilities": len(capabilities),
        "structured_capabilities": len(structured),
        "verifiable": len(structured) == len(capabilities) and len(capabilities) > 0,
    }


# ----------------------------------------------------------------------------
# Mechanism 2 — performance-based trust scores
# ----------------------------------------------------------------------------

@dataclass
class TrustScore:
    """
    Every tool begins neutral (0.5). Successful executions increase trust;
    failures, high latency, or degradations decrease it. A meritocracy where
    the orchestrator prioritizes consistently reliable tools.
    """

    score: float = 0.5
    successes: int = 0
    failures: int = 0
    latency_penalties: int = 0
    slow_threshold_ms: float = 2000.0
    step: float = 0.05

    def record(self, success: bool, latency_ms: float) -> None:
        if success:
            self.successes += 1
            self.score = min(1.0, self.score + self.step)
        else:
            self.failures += 1
            self.score = max(0.0, self.score - self.step)
        if latency_ms > self.slow_threshold_ms:
            self.latency_penalties += 1
            # TODO(production): weight the latency penalty by how far over the
            # SLO the call ran, and decay old observations so a tool that
            # recovers regains trust.
            self.score = max(0.0, self.score - self.step / 2)

    def as_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "successes": self.successes,
            "failures": self.failures,
            "latency_penalties": self.latency_penalties,
        }


# ----------------------------------------------------------------------------
# The DRAFT loop — simulated tool behavior
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Observation:
    probe: str
    success: bool
    latency_ms: float
    error: str | None


def _simulate(tool: dict, probe: str) -> Observation:
    """
    Simulate the REAL behavior of the tool from declarative rules. This stands
    in for issuing an actual call in production. The rules deliberately diverge
    from the claimed documentation so DRAFT has a gap to discover.
    """
    b = tool.get("behavior", {})
    base = float(b.get("base_latency_ms", 50))
    per_char = float(b.get("latency_per_char_ms", 0.0))
    latency = base + per_char * len(probe)

    if b.get("rejects_empty", False) and probe == "":
        return Observation(probe, False, latency, "empty input rejected")
    max_len = b.get("max_len")
    if max_len is not None and len(probe) > int(max_len):
        return Observation(probe, False, latency, f"input over {max_len} chars rejected")
    if b.get("ascii_only", False) and not probe.isascii():
        return Observation(probe, False, latency, "non-ASCII input rejected")
    return Observation(probe, True, latency, None)


def gather_experience(tool: dict, probes: Iterable[str]) -> list[Observation]:
    """
    DRAFT phase 1 — Experience Gathering. Probe tool boundaries with a DIVERSE
    set of inputs (dedup enforced to avoid redundant tests), recording success,
    latency, and discovered failure modes.
    """
    seen: set[str] = set()
    observations: list[Observation] = []
    for probe in probes:
        if probe in seen:  # diversity enforcement — no redundant tests
            continue
        seen.add(probe)
        observations.append(_simulate(tool, probe))
    return observations


def learn_from_experience(tool: dict, observations: list[Observation]) -> dict:
    """
    DRAFT phase 2 — Learning from Experience. Analyze the GAP between the claimed
    documentation and observed reality. Systematic discovery of true
    capabilities, not error logging.
    """
    claim = tool.get("claimed_description", "")
    failures = [o for o in observations if not o.success]
    discovered_errors = sorted({o.error for o in failures if o.error})

    # Discovered constraints from observed successes/failures.
    max_ok = max((len(o.probe) for o in observations if o.success), default=0)
    min_failed_len = min((len(o.probe) for o in failures), default=None)
    latencies = [o.latency_ms for o in observations]
    latency_varies = (max(latencies) - min(latencies)) > 1.0 if latencies else False

    # Gap detection: does the claim over-promise relative to what we saw?
    over_promises_any_text = (
        bool(re.search(r"\bany (text|input|string)\b", claim, re.IGNORECASE))
        and bool(discovered_errors)
    )
    return {
        "tool": tool.get("name"),
        "claim": claim,
        "probes_run": len(observations),
        "failures": len(failures),
        "discovered_error_conditions": discovered_errors,
        "max_successful_len": max_ok,
        "first_failing_len": min_failed_len,
        "latency_payload_dependent": latency_varies,
        "gap_over_promises_any_text": over_promises_any_text,
        "converged": len(discovered_errors) == 0,
    }


def rewrite_documentation(tool: dict, learning: dict) -> dict:
    """
    DRAFT phase 3 — Documentation Rewriting. Generate an AI-optimized spec
    reflecting the discovered reality: parameter ranges, error conditions, and
    real performance characteristics. Replaces the vague human-friendly claim.

    # TODO(production): the rewrite is generated by an LLM prompted with the
    # observations. Here we assemble it deterministically from the learning
    # dict so the loop is reproducible.
    """
    b = tool.get("behavior", {})
    constraints = []
    if b.get("rejects_empty"):
        constraints.append("input must be non-empty")
    if b.get("max_len") is not None:
        constraints.append(f"input length <= {b['max_len']} characters")
    if b.get("ascii_only"):
        constraints.append("input must be ASCII (non-ASCII rejected)")
    perf = "latency scales with payload size" if learning["latency_payload_dependent"] \
        else "latency roughly constant"
    return {
        "name": tool.get("name"),
        "refined_description": (
            f"{tool.get('name')}: {tool.get('true_purpose', 'performs its function')}. "
            f"Constraints: {'; '.join(constraints) if constraints else 'none observed'}. "
            f"Performance: {perf}."
        ),
        "error_conditions": learning["discovered_error_conditions"],
        "observed_max_input_len": learning["max_successful_len"],
        "performance": perf,
    }


def run_draft(tool: dict, probes: Iterable[str]) -> dict:
    """
    Full DRAFT loop: gather -> learn -> rewrite. Returns the refined spec plus
    the learning gap. In production this iterates until the doc converges; a
    single pass over a diverse probe set is enough to surface the gap here.
    """
    observations = gather_experience(tool, probes)
    learning = learn_from_experience(tool, observations)
    refined = rewrite_documentation(tool, learning)
    return {
        "observations": [o.__dict__ for o in observations],
        "learning": learning,
        "refined_spec": refined,
    }
