#!/usr/bin/env python3
"""intervention-selector CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    Intervention,
    INTENSITY,
    INTERVENTION_TYPES,
    explain,
    intervention_intensity,
    risk_rank,
    select_intervention,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "intervention-selector primitive (Ch7)"
    text = SKILL_MD.read_text(encoding="utf-8")
    desc = []
    in_desc = False
    fm_count = 0
    in_frontmatter = False
    for line in text.splitlines():
        if line.strip() == "---":
            fm_count += 1
            in_frontmatter = fm_count == 1
            if fm_count == 2:
                break
            continue
        if not in_frontmatter:
            continue
        if line.startswith("description:"):
            in_desc = True
            continue
        if in_desc:
            if line and not line[0].isspace():
                in_desc = False
                continue
            desc.append(line.strip())
    return " ".join(d for d in desc if d) or "intervention-selector (Ch7)"


# The DevOps prediction failure report (the chapter's premature-closure diagnostic).
# stripe-python 3.2.1 -> 3.3.0 deploy across checkout-service -> order-service
# -> fulfillment-service (fictional AWS account 123456789012); the changelog
# reduced default connection_timeout 30s -> 10s. The agent committed to an "API
# contract violation" hypothesis at step 4 and reinforced it at step 5, a
# premature-closure reasoning failure, not a knowledge gap.
DEVOPS_REPORT = {
    "execution_id": "pred_7f3a9c",
    "layer_1_context": {"sufficient": True, "confidence": 0.97},
    "layer_2_cognitive": {
        "failure_type": "REASONING",
        "fault_location": {"node_id": "CausalAttributionNode"},
        "knowledge_index": 0.91,
        "low_infogain_steps": [4, 5],
        "diagnosis": (
            "Premature commitment to 'API contract violation' at step 4. "
            "Configuration change (timeout reduction 30s->10s) had equal "
            "evidentiary support but was not explored after early commitment."
        ),
    },
    "recommended_intervention": "PROMPT_REFINEMENT",
    "target_nodes": ["CausalAttributionNode"],
}


def _load_report(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_select(args):
    report = _load_report(args.path)
    itv = select_intervention(report)
    print(json.dumps(itv.to_dict(), indent=2, default=str))


def cmd_intensity(args):
    if args.type is None:
        print(json.dumps(INTENSITY, indent=2))
        return
    if args.type not in INTERVENTION_TYPES:
        print(f"unknown intervention type: {args.type}", file=sys.stderr)
        print(f"expected one of: {', '.join(INTERVENTION_TYPES)}", file=sys.stderr)
        sys.exit(1)
    profile = intervention_intensity(args.type)
    profile["risk_rank"] = risk_rank(args.type)
    print(json.dumps({args.type: profile}, indent=2))


def cmd_explain(args):
    report = _load_report(args.path)
    print(explain(report))


def cmd_scenario(args):
    if args.name != "devops-prediction":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        print("available scenarios: devops-prediction", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps prediction failure - intervention routing")
    print("=" * 70)
    print("Incident: stripe-python 3.2.1 -> 3.3.0 deploy across")
    print("  checkout-service -> order-service -> fulfillment-service")
    print("  (AWS account 123456789012). Changelog reduced default")
    print("  connection_timeout 30s -> 10s.")
    print("Diagnosis: premature-closure REASONING failure at CausalAttributionNode,")
    print("  steps 4 and 5; knowledge_index 0.91, context sufficient.")
    print("-" * 70)
    itv = select_intervention(DEVOPS_REPORT)
    print(json.dumps(itv.to_dict(), indent=2, default=str))
    print("-" * 70)
    print(explain(DEVOPS_REPORT))
    intensity = intervention_intensity(itv.type)
    print("-" * 70)
    print(
        f"Intensity: {intensity['tier']} tier, {intensity['speed']} to apply, "
        f"{intensity['reversibility']}, {intensity['risk']} risk."
    )
    if itv.type != "PROMPT_REFINEMENT":
        print(
            f"UNEXPECTED: DevOps report resolved to {itv.type}, "
            "expected PROMPT_REFINEMENT",
            file=sys.stderr,
        )
        sys.exit(1)
    print("Resolved to PROMPT_REFINEMENT (expected). The lightest intervention:")
    print("  a reasoning pattern localized to one node, not a knowledge gap.")


def cmd_benchmark(args):
    failures = []

    def check(label, cond):
        if not cond:
            failures.append(label)

    # Test 1: insufficient context -> RETRIEVAL_FIX (short-circuits everything).
    r1 = {
        "layer_1_context": {"sufficient": False},
        "layer_2_cognitive": {"failure_type": "FORMAT_VIOLATION"},
        "target_nodes": ["N1"],
    }
    i1 = select_intervention(r1)
    check(
        f"insufficient context should route RETRIEVAL_FIX, got {i1.type}",
        i1.type == "RETRIEVAL_FIX" and i1.target == "retrieval_pipeline",
    )

    # Test 2: FORMAT_VIOLATION (context sufficient) -> STRUCTURAL_CONSTRAINT.
    r2 = {
        "layer_1_context": {"sufficient": True},
        "layer_2_cognitive": {"failure_type": "FORMAT_VIOLATION"},
        "target_nodes": ["ExtractorNode"],
    }
    i2 = select_intervention(r2)
    check(
        f"FORMAT_VIOLATION should route STRUCTURAL_CONSTRAINT, got {i2.type}",
        i2.type == "STRUCTURAL_CONSTRAINT"
        and i2.action == "Attach output schema to node"
        and i2.target == ["ExtractorNode"],
    )

    # Test 3: REASONING, 2 low steps, ki 0.91 -> PROMPT_REFINEMENT.
    r3 = {
        "layer_1_context": {"sufficient": True},
        "layer_2_cognitive": {
            "failure_type": "REASONING",
            "low_infogain_steps": [4, 5],
            "knowledge_index": 0.91,
        },
        "target_nodes": ["CausalAttributionNode"],
    }
    i3 = select_intervention(r3)
    check(
        f"REASONING/2-low/ki0.91 should route PROMPT_REFINEMENT, got {i3.type}",
        i3.type == "PROMPT_REFINEMENT"
        and i3.action == "Update prompt for target node",
    )

    # Test 4: REASONING with 4 low steps -> FINE_TUNE (too many low steps).
    r4 = {
        "layer_1_context": {"sufficient": True},
        "layer_2_cognitive": {
            "failure_type": "REASONING",
            "low_infogain_steps": [2, 3, 4, 5],
            "knowledge_index": 0.91,
        },
        "target_nodes": ["CausalAttributionNode"],
    }
    i4 = select_intervention(r4)
    check(
        f"REASONING with 4 low steps should route FINE_TUNE, got {i4.type}",
        i4.type == "FINE_TUNE",
    )

    # Test 5: KNOWLEDGE failure with low KI -> FINE_TUNE (systemic gap).
    r5 = {
        "layer_1_context": {"sufficient": True},
        "layer_2_cognitive": {
            "failure_type": "KNOWLEDGE",
            "low_infogain_steps": [],
            "knowledge_index": 0.42,
        },
        "target_nodes": ["N5"],
    }
    i5 = select_intervention(r5)
    check(
        f"KNOWLEDGE/low-ki should route FINE_TUNE, got {i5.type}",
        i5.type == "FINE_TUNE"
        and i5.action == "Generate curriculum via SEAL/TPT and retrain",
    )

    # Test 6: intensity hierarchy ordering prompt < fine-tune < code-mod by risk.
    rp = risk_rank("PROMPT_REFINEMENT")
    rf = risk_rank("FINE_TUNE")
    rc = risk_rank("CODE_MODIFICATION")
    check(
        f"risk ordering prompt<finetune<codemod broken: {rp},{rf},{rc}",
        rp < rf < rc,
    )

    # Test 7: the DevOps scenario report resolves to PROMPT_REFINEMENT.
    idev = select_intervention(DEVOPS_REPORT)
    check(
        f"DevOps report should resolve PROMPT_REFINEMENT, got {idev.type}",
        idev.type == "PROMPT_REFINEMENT"
        and idev.target == ["CausalAttributionNode"],
    )

    # Test 8: KI boundary. ki exactly at floor (0.8) is NOT > floor -> FINE_TUNE.
    r8 = {
        "layer_1_context": {"sufficient": True},
        "layer_2_cognitive": {
            "failure_type": "REASONING",
            "low_infogain_steps": [1],
            "knowledge_index": 0.8,
        },
        "target_nodes": ["N8"],
    }
    check(
        "ki == floor should fall through to FINE_TUNE (strict > floor)",
        select_intervention(r8).type == "FINE_TUNE",
    )

    # Test 9: low-step boundary. Exactly low_step_max (2) qualifies (<=) -> PROMPT.
    r9 = {
        "layer_1_context": {"sufficient": True},
        "layer_2_cognitive": {
            "failure_type": "REASONING",
            "low_infogain_steps": [1, 2],
            "knowledge_index": 0.95,
        },
        "target_nodes": ["N9"],
    }
    check(
        "low_infogain_steps count == low_step_max should route PROMPT_REFINEMENT",
        select_intervention(r9).type == "PROMPT_REFINEMENT",
    )

    # Test 10: threshold override. Loosening low_step_max reroutes r4 to PROMPT.
    i10 = select_intervention(r4, low_step_max=4)
    check(
        f"loosened low_step_max should reroute 4-low-steps to PROMPT, got {i10.type}",
        i10.type == "PROMPT_REFINEMENT",
    )

    # Test 11: precedence. Insufficient context wins over FORMAT_VIOLATION.
    check(
        "insufficient context must take precedence over FORMAT_VIOLATION",
        select_intervention(r1).type == "RETRIEVAL_FIX",
    )

    # Test 12: defensive missing keys. No low_infogain_steps / knowledge_index.
    r12 = {
        "layer_1_context": {"sufficient": True},
        "layer_2_cognitive": {"failure_type": "REASONING"},
        "target_nodes": ["N12"],
    }
    check(
        "missing low_infogain_steps/knowledge_index defaults ([]/1.0) -> PROMPT",
        select_intervention(r12).type == "PROMPT_REFINEMENT",
    )

    # Test 13: intensity profile shape (all five keys present per type).
    keys = {"tier", "speed", "reversibility", "risk", "description"}
    for t in INTERVENTION_TYPES:
        prof = intervention_intensity(t)
        check(f"intensity[{t}] missing keys", keys.issubset(prof.keys()))

    # Test 14: unknown intensity type raises ValueError.
    try:
        intervention_intensity("NOPE")
        failures.append("intervention_intensity('NOPE') should raise ValueError")
    except ValueError:
        pass

    # Test 15: to_dict round-trip preserves the intervention.
    itv = select_intervention(r3)
    rebuilt = Intervention.from_dict(itv.to_dict())
    check("Intervention to_dict/from_dict round-trip differs", rebuilt == itv)

    # Test 16: explain returns an auditable line naming type + execution_id.
    line = explain(DEVOPS_REPORT)
    check(
        "explain() must name execution_id and chosen intervention",
        "pred_7f3a9c" in line and "PROMPT_REFINEMENT" in line,
    )

    total = 16
    print("=" * 70)
    print(f"intervention-selector benchmark - {total - len(failures)}/{total} passed")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for x in failures:
            print(f"  - {x}")
        sys.exit(1)
    print("All gates passed.")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description=_skill_description())
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sel = sub.add_parser("select", help="Route a diagnostic report to one intervention")
    p_sel.add_argument("--path", required=True, help="path to a diagnostic report JSON")
    p_sel.set_defaults(func=cmd_select)

    p_int = sub.add_parser("intensity", help="Show the intensity profile for a type")
    p_int.add_argument(
        "--type",
        default=None,
        help=f"one of {', '.join(INTERVENTION_TYPES)}; omit for all",
    )
    p_int.set_defaults(func=cmd_intensity)

    p_exp = sub.add_parser("explain", help="Print the audit line for a report")
    p_exp.add_argument("--path", required=True, help="path to a diagnostic report JSON")
    p_exp.set_defaults(func=cmd_explain)

    p_scn = sub.add_parser("scenario", help="Run the DevOps prediction running example")
    p_scn.add_argument("name", help="scenario name (devops-prediction)")
    p_scn.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
