#!/usr/bin/env python3
"""
federated-context-governance — multi-harness CLI wrapper.

    federated-context-governance --help
    federated-context-governance drift
    federated-context-governance stage
    federated-context-governance federate
    federated-context-governance effective backend-eng
    federated-context-governance layer enterprise
    federated-context-governance benchmark

The CLI mirrors the SKILL.md Process section step by step so any harness that
runs CLI tools (cron, CI, Claude Code, Cursor, Gemini CLI, Windsurf, OpenCode)
gets the same behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lib  # noqa: E402

DEFAULT_GOV = HERE / "sample-governance.json"
SKILL_DESCRIPTION = (
    "Govern agent-configuration drift across a team. Detects where "
    "independently-authored context configs diverge, enforces a FEDERATED org "
    "base whose nonnegotiable settings every team must inherit unchanged, and "
    "routes a governance need to the right architectural layer (Config-as-Code "
    "for teams, Shared Knowledge Layer for departments, Governance Control Plane "
    "for the enterprise)."
)


def cmd_drift(args: argparse.Namespace) -> int:
    gov = lib.load_governance(args.governance)
    result = lib.detect_drift(gov["team_configs"])
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"Configs compared: {result['configs']}")
    print(f"Drifted settings: {result['drifted_setting_count']}\n")
    for key, owners in result["drifted_settings"].items():
        print(f"  {key}:")
        for owner, val in owners.items():
            print(f"    {owner:<18} = {val}")
    if result["partial_skills"]:
        print("\nSkills present in some configs but not others:")
        for skill, owners in result["partial_skills"].items():
            print(f"  {skill:<30} {owners}")
    return 0


def cmd_stage(args: argparse.Namespace) -> int:
    gov = lib.load_governance(args.governance)
    result = lib.fragmentation_stage(gov["team_configs"])
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"Fragmentation stage: {result['stage']}")
    print(f"  configs={result['configs']}  drifted_settings={result['drifted_settings']}"
          f"  partial_skills={result['partial_skills']}")
    print("\nProgression: individual optimization -> silent divergence "
          "-> visible inconsistency -> coordination overhead")
    return 0


def cmd_federate(args: argparse.Namespace) -> int:
    gov = lib.load_governance(args.governance)
    result = lib.check_federation(gov["org_base"], gov["team_configs"])
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"Nonnegotiable org keys: {result['nonnegotiable_keys']}")
    print(f"All teams compliant: {result['all_compliant']}"
          f"  (violations: {result['violation_count']})\n")
    for team in result["teams"]:
        status = "OK" if team["compliant"] else "VIOLATION"
        print(f"  [{status}] {team['owner']}")
        for v in team["violations"]:
            print(f"      {v['key']}: org={v['org_value']} team={v['team_value']}")
    return 0


def cmd_effective(args: argparse.Namespace) -> int:
    gov = lib.load_governance(args.governance)
    team = next((t for t in gov["team_configs"] if t.get("owner") == args.owner), None)
    if team is None:
        print(f"No team config for owner {args.owner!r}", file=sys.stderr)
        return 2
    result = lib.resolve_effective_config(gov["org_base"], team)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"Effective config for {result['owner']} (locked keys: {result['locked_keys']}):\n")
    for k, v in result["effective_settings"].items():
        locked = "  [locked]" if k in result["locked_keys"] else ""
        print(f"  {k:<26} = {v}{locked}")
    print(f"\n  skills: {result['skills']}")
    return 0


def cmd_layer(args: argparse.Namespace) -> int:
    try:
        result = lib.recommend_layer(args.scale)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"Scale: {result['scale']}")
    print(f"  layer:      {result['layer']}")
    print(f"  tool:       {result['tool']}")
    print(f"  mechanism:  {result['mechanism']}")
    print(f"  composes with (inherits): {result['composes_with']}")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """
    Prove: drift is detected across teams, the fragmentation stage reflects it,
    and the seeded nonnegotiable violation (rogue-frontend disabling
    code_review_required) is caught by federation enforcement.
    """
    gov = lib.load_governance(args.governance)
    drift = lib.detect_drift(gov["team_configs"])
    stage = lib.fragmentation_stage(gov["team_configs"])
    fed = lib.check_federation(gov["org_base"], gov["team_configs"])

    rogue = next((t for t in fed["teams"] if t["owner"] == "rogue-frontend"), None)
    rogue_caught = rogue is not None and not rogue["compliant"] and any(
        v["key"] == "code_review_required" for v in rogue["violations"]
    )

    if args.json:
        print(json.dumps({
            "drifted_setting_count": drift["drifted_setting_count"],
            "fragmentation_stage": stage["stage"],
            "all_teams_compliant": fed["all_compliant"],
            "violation_count": fed["violation_count"],
            "rogue_code_review_violation_caught": rogue_caught,
        }, indent=2))
        return 0
    print("Federated context governance benchmark\n")
    print(f"drifted settings detected: {drift['drifted_setting_count']} "
          f"({sorted(drift['drifted_settings'])})")
    print(f"fragmentation stage: {stage['stage']}")
    print(f"all teams compliant with nonnegotiable base: {fed['all_compliant']}")
    print(f"total nonnegotiable violations: {fed['violation_count']}")
    print(f"rogue-frontend code_review_required violation caught: {rogue_caught}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="federated-context-governance", description=SKILL_DESCRIPTION
    )
    parser.add_argument("--governance", type=str, default=str(DEFAULT_GOV))
    sub = parser.add_subparsers(dest="command", required=True)

    p_d = sub.add_parser("drift", help="Detect configuration drift across team configs")
    p_d.add_argument("--json", action="store_true")
    p_d.set_defaults(func=cmd_drift)

    p_s = sub.add_parser("stage", help="Report the fragmentation-progression stage")
    p_s.add_argument("--json", action="store_true")
    p_s.set_defaults(func=cmd_stage)

    p_f = sub.add_parser("federate", help="Enforce the nonnegotiable org base; flag violations")
    p_f.add_argument("--json", action="store_true")
    p_f.set_defaults(func=cmd_federate)

    p_e = sub.add_parser("effective", help="Resolve a team's effective config (base + overrides, locked)")
    p_e.add_argument("owner", type=str, help="Team/developer owner name")
    p_e.add_argument("--json", action="store_true")
    p_e.set_defaults(func=cmd_effective)

    p_l = sub.add_parser("layer", help="Recommend the governance layer for a scale")
    p_l.add_argument("scale", type=str, choices=["team", "department", "enterprise"])
    p_l.add_argument("--json", action="store_true")
    p_l.set_defaults(func=cmd_layer)

    p_b = sub.add_parser("benchmark", help="Prove drift detection + federation enforcement")
    p_b.add_argument("--json", action="store_true")
    p_b.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
