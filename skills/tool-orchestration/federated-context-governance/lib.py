"""
Federated context governance — detect configuration drift, enforce a federated
org base, and route a governance need to the right architectural layer.

Distilled from Agentic Graph RAG (O'Reilly), Chapter 6 — Tool Orchestration
("Context Governance: The Missing Layer in Tool Orchestration").

The problem: configuration drift at scale. When one developer configures an AI
coding agent (a CLAUDE.md, installed skills, hooks) the result is coherent. When
five developers do it independently, the result is five divergent architectures —
each agent gets different instructions, applies different patterns, and produces
code shaped by different assumptions. Marc Baselga documented this; Ben Erez
called it the "unexpected tax". The fragmentation follows a predictable
progression:

    individual optimization -> silent divergence -> visible inconsistency
    -> coordination overhead

The chapter's three solution architectures map to organizational scale and are
LAYERS of one federated architecture, not competing options (Table 6-4):

    Team scale       Configuration as Code   (Meppiel APM)     -- versioned,
                                                                  composable
                                                                  config packages
    Department scale Shared Knowledge Layer  (Rakhmetzhanov Nia)-- central indexed
                                                                  knowledge base
    Enterprise scale Governance Control Plane(Jarjoura Runtime) -- business rules,
                                                                  constraints,
                                                                  ownership as
                                                                  infrastructure

The architecture is FEDERATED, not centralized: teams own domain-specific context
but inherit an organizational base that encodes nonnegotiable standards (security
policies, architectural constraints, code-review requirements, compliance rules).
Jarjoura's diagnosis: "Context failure, not AI failure." Agents amplify whatever
structure they receive; if the structure is inconsistent, agents amplify ambiguity.

STDLIB ONLY.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def load_governance(path: str | Path) -> dict:
    """
    Load the governance document: an org_base (with a nonnegotiable subset) plus
    a list of team/developer context configs.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------
# Configuration drift detection
# ----------------------------------------------------------------------------

def detect_drift(configs: list[dict]) -> dict:
    """
    Find settings where independently-authored configs disagree — the silent
    divergence the chapter describes. A key that appears in >= 2 configs with
    differing values is drift. Skills present in some configs but not others are
    reported separately.
    """
    # Collect every setting value seen per key.
    values_by_key: dict[str, dict] = {}
    for cfg in configs:
        owner = cfg.get("owner", "unknown")
        for k, v in cfg.get("settings", {}).items():
            values_by_key.setdefault(k, {})[owner] = v

    drifted = {}
    for key, owner_values in values_by_key.items():
        distinct = {json.dumps(v, sort_keys=True) for v in owner_values.values()}
        if len(owner_values) >= 2 and len(distinct) > 1:
            drifted[key] = owner_values

    # Skill divergence.
    skills_by_owner = {c.get("owner", "unknown"): set(c.get("skills", [])) for c in configs}
    all_skills: set[str] = set()
    for s in skills_by_owner.values():
        all_skills |= s
    partial_skills = {
        skill: sorted([o for o, s in skills_by_owner.items() if skill in s])
        for skill in sorted(all_skills)
        if 0 < sum(skill in s for s in skills_by_owner.values()) < len(skills_by_owner)
    }

    return {
        "configs": len(configs),
        "drifted_settings": drifted,
        "drifted_setting_count": len(drifted),
        "partial_skills": partial_skills,
    }


def fragmentation_stage(configs: list[dict]) -> dict:
    """
    Map the observed drift to the chapter's four-stage fragmentation progression.
    A single config is coherent by definition; more configs + more drift move the
    system down the progression.
    """
    n = len(configs)
    drift = detect_drift(configs)
    d = drift["drifted_setting_count"]
    partial = len(drift["partial_skills"])

    if n <= 1:
        stage = "individual optimization"
    elif d == 0 and partial == 0:
        stage = "individual optimization"
    elif d <= 1 and partial <= 1:
        stage = "silent divergence"
    elif d <= 3:
        stage = "visible inconsistency"
    else:
        stage = "coordination overhead"
    return {
        "stage": stage,
        "configs": n,
        "drifted_settings": d,
        "partial_skills": partial,
    }


# ----------------------------------------------------------------------------
# Federated enforcement — teams inherit the nonnegotiable org base
# ----------------------------------------------------------------------------

def check_federation(org_base: dict, team_configs: list[dict]) -> dict:
    """
    Enforce the federated model: teams own their domain-specific context but MUST
    inherit the organizational base's nonnegotiable settings unchanged. A team
    that overrides a nonnegotiable (security, architectural, compliance) key is a
    violation. Teams may freely add or override NEGOTIABLE keys.
    """
    base_settings = org_base.get("settings", {})
    nonneg = set(org_base.get("nonnegotiable", []))

    results = []
    for team in team_configs:
        owner = team.get("owner", "unknown")
        team_settings = team.get("settings", {})
        violations = []
        missing = []
        for key in nonneg:
            if key not in team_settings:
                # Inherited implicitly is fine; flag only if the team set it wrong.
                missing.append(key)
                continue
            if json.dumps(team_settings[key], sort_keys=True) != \
               json.dumps(base_settings.get(key), sort_keys=True):
                violations.append({
                    "key": key,
                    "org_value": base_settings.get(key),
                    "team_value": team_settings[key],
                })
        results.append({
            "owner": owner,
            "violations": violations,
            "inherits_implicitly": missing,
            "compliant": len(violations) == 0,
        })

    return {
        "nonnegotiable_keys": sorted(nonneg),
        "teams": results,
        "all_compliant": all(r["compliant"] for r in results),
        "violation_count": sum(len(r["violations"]) for r in results),
    }


def resolve_effective_config(org_base: dict, team: dict) -> dict:
    """
    Compute a team's EFFECTIVE config: the org base overlaid with the team's
    negotiable overrides, with nonnegotiable keys locked to the base value. This
    is the coherent per-team context a federated architecture produces.
    """
    base_settings = dict(org_base.get("settings", {}))
    nonneg = set(org_base.get("nonnegotiable", []))
    effective = dict(base_settings)
    for k, v in team.get("settings", {}).items():
        if k in nonneg:
            continue  # locked to base — team override ignored
        effective[k] = v
    return {
        "owner": team.get("owner", "unknown"),
        "effective_settings": effective,
        "locked_keys": sorted(nonneg),
        "skills": sorted(set(org_base.get("skills", [])) | set(team.get("skills", []))),
    }


# ----------------------------------------------------------------------------
# Layer routing — which solution architecture fits the scale
# ----------------------------------------------------------------------------

_LAYERS = {
    "team": {
        "layer": "Configuration as Code",
        "tool": "APM (Agent Package Manager, Meppiel)",
        "mechanism": "declarative manifest of versioned, composable skill/rule/prompt packages; every developer runs apm install for the same base, team extensions compose on top",
    },
    "department": {
        "layer": "Shared Knowledge Layer",
        "tool": "Nia Skills (Rakhmetzhanov)",
        "mechanism": "a central indexed knowledge base (repos, docs, research) that any agent queries through a standardized interface instead of each developer curating their own context",
    },
    "enterprise": {
        "layer": "Governance Control Plane",
        "tool": "Runtime (Jarjoura)",
        "mechanism": "a persistent governance layer above orchestration encoding business rules, architectural constraints, ownership boundaries, and historical decisions as infrastructure",
    },
}


def recommend_layer(scale: str) -> dict:
    """
    Route a governance need to the architectural layer that fits its scale. The
    three layers compose (federated), so a larger scale inherits the smaller
    ones beneath it.
    """
    scale = scale.lower()
    if scale not in _LAYERS:
        raise ValueError(f"scale must be one of {sorted(_LAYERS)}; got {scale!r}")
    order = ["team", "department", "enterprise"]
    idx = order.index(scale)
    return {
        "scale": scale,
        **_LAYERS[scale],
        "composes_with": order[: idx + 1],  # inherits the layers beneath it
    }
