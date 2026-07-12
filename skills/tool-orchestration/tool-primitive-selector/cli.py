#!/usr/bin/env python3
"""tool-primitive-selector CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    Capability, score_primitives, recommend_primitive, gradient_position,
    AXES, PRIMITIVES,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "tool-primitive-selector (Ch6)"
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
    return " ".join(d for d in desc if d) or "tool-primitive-selector"


def _cap_from_args(args) -> Capability:
    return Capability(
        audience=args.audience,
        invocation=args.invocation,
        needs_per_agent_access_control=args.access_control,
        needs_model_to_invoke=args.needs_model,
        composability_need=args.composability,
    )


def cmd_recommend(args):
    print(json.dumps(recommend_primitive(_cap_from_args(args)), indent=2))


def cmd_score(args):
    print(json.dumps(dict(score_primitives(_cap_from_args(args))), indent=2))


def cmd_gradient(args):
    print(json.dumps(gradient_position(args.audience), indent=2))


_SCENARIOS = {
    # A deterministic deployment tool rolled out enterprise-wide with
    # per-agent access control: MCP primary (governed endpoint), also CLI.
    "enterprise-deploy-tool": Capability(
        audience="enterprise", invocation="deterministic_command",
        needs_per_agent_access_control=True, needs_model_to_invoke=False,
        composability_need=1,
    ),
    # A code-review procedure -- the value is judgment (what to check, in what
    # order), not a callable endpoint: SKILL.
    "code-review-procedure": Capability(
        audience="team", invocation="judgment_guidance",
        needs_per_agent_access_control=False, needs_model_to_invoke=True,
    ),
}


def cmd_scenario(args):
    if args.name not in _SCENARIOS:
        print(f"unknown scenario: {args.name} "
              f"(known: {', '.join(sorted(_SCENARIOS))})", file=sys.stderr)
        sys.exit(1)
    cap = _SCENARIOS[args.name]
    print("=" * 70)
    print(f"Scenario: {args.name}")
    print("=" * 70)
    print(json.dumps(recommend_primitive(cap), indent=2))


def cmd_benchmark(args):
    failures = []

    def rec(**kw):
        return recommend_primitive(Capability(**kw))

    # Test 1: a deterministic command for an individual -> CLI.
    if rec(audience="individual", invocation="deterministic_command")["recommended"] != "cli":
        failures.append("individual + deterministic_command should pick cli")

    # Test 2: runtime agent discovery at enterprise scale with access control -> MCP.
    r = rec(audience="enterprise", invocation="runtime_agent_discovery",
            needs_per_agent_access_control=True, needs_model_to_invoke=True)
    if r["recommended"] != "mcp":
        failures.append("enterprise + runtime discovery + access_control should pick mcp")

    # Test 3: judgment guidance -> SKILL, regardless of audience.
    for aud in ("individual", "team", "enterprise"):
        if rec(audience=aud, invocation="judgment_guidance",
               needs_model_to_invoke=True)["recommended"] != "skill":
            failures.append(f"judgment_guidance ({aud}) should pick skill")

    # Test 4: convergence -- an enterprise governed deterministic capability
    # surfaces BOTH mcp and cli (one recommended, the other in also_expose_as).
    r = rec(audience="enterprise", invocation="deterministic_command",
            needs_per_agent_access_control=True)
    surfaced = {r["recommended"], *r["also_expose_as"]}
    if not {"mcp", "cli"}.issubset(surfaced):
        failures.append(f"enterprise deterministic should surface both mcp+cli, got {surfaced}")
    if r["recommended"] != "mcp":
        failures.append("enterprise governed deterministic should make mcp primary")

    # Test 5: neutral capability does not crash; all primitives scored.
    scored = score_primitives(Capability())
    if len(scored) != len(PRIMITIVES):
        failures.append("all primitives must be scored")

    # Test 6: high Unix-pipe composability tips an individual to CLI.
    if rec(audience="individual", invocation="deterministic_command",
           composability_need=3)["recommended"] != "cli":
        failures.append("high composability should pick cli")

    # Test 7: gradient position -- individual is cli-biased/personal;
    # enterprise is mcp-biased with per-agent access control governance.
    gi = gradient_position("individual")
    ge = gradient_position("enterprise")
    if gi["primitive_bias"] != "cli" or gi["position"] != "personal":
        failures.append("individual gradient should be personal / cli-biased")
    if ge["primitive_bias"] != "mcp" or "access control" not in ge["governance"].lower():
        failures.append("enterprise gradient should be mcp-biased with access-control governance")

    # Test 8: a deterministic no-model surface is NOT a skill (skills need a
    # model to read the judgment; a scripting surface does not).
    r = rec(audience="individual", invocation="deterministic_command",
            needs_model_to_invoke=False)
    if r["recommended"] == "skill":
        failures.append("no-model deterministic surface should not be a skill")

    # Test 9: primitive set is exactly the three chapter primitives.
    if set(PRIMITIVES) != {"cli", "mcp", "skill"}:
        failures.append("primitive set drifted from cli/mcp/skill")
    if len(AXES) != 6:
        failures.append("axis set drifted from the 6 chapter axes")

    # Test 10: also_expose_as never duplicates the recommended primitive.
    for cap in (Capability(audience="enterprise", invocation="deterministic_command",
                           needs_per_agent_access_control=True),
                Capability(audience="individual", invocation="judgment_guidance"),
                Capability(audience="team", invocation="runtime_agent_discovery")):
        r = recommend_primitive(cap)
        if r["recommended"] in r["also_expose_as"]:
            failures.append("also_expose_as must not contain the recommended primitive")
            break

    total = 10
    print("=" * 70)
    print(f"tool-primitive-selector benchmark - {total - len(failures)}/{total} passed")
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

    def add_cap_args(p):
        p.add_argument("--audience", default="individual",
                       choices=["individual", "team", "enterprise"])
        p.add_argument("--invocation", default="deterministic_command",
                       choices=["deterministic_command", "runtime_agent_discovery",
                                "judgment_guidance"])
        p.add_argument("--access-control", dest="access_control",
                       action="store_true",
                       help="needs per-agent access control (MCP governance)")
        p.add_argument("--needs-model", dest="needs_model", action="store_true",
                       help="a model must be in the loop to invoke")
        p.add_argument("--composability", type=int, default=0,
                       help="Unix-pipe composability need 0..3")

    p_rec = sub.add_parser("recommend", help="Recommend a primitive from a capability profile")
    add_cap_args(p_rec)
    p_rec.set_defaults(func=cmd_recommend)

    p_score = sub.add_parser("score", help="Score all three primitives for a capability")
    add_cap_args(p_score)
    p_score.set_defaults(func=cmd_score)

    p_grad = sub.add_parser("gradient", help="Where an audience sits on the personal-to-enterprise gradient")
    p_grad.add_argument("audience", choices=["individual", "team", "enterprise"])
    p_grad.set_defaults(func=cmd_gradient)

    p_scen = sub.add_parser("scenario", help="Worked scenario (enterprise-deploy-tool | code-review-procedure)")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
