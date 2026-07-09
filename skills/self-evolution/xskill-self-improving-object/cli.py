#!/usr/bin/env python3
"""xskill-self-improving-object CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    AgentExperience,
    SkillGraph,
    SkillNode,
    extract_experiences,
    extract_skills,
    flag_stale_skills,
    retire_experiences,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "xskill-self-improving-object (Ch7)"
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
    return " ".join(d for d in desc if d) or "xskill-self-improving-object (Ch7)"


def cmd_extract(args):
    with open(args.path, encoding="utf-8") as f:
        data = json.load(f)
    nodes = data.get("execution_nodes", [])
    execs = data.get("successful_executions", [])
    min_support = data.get("min_support", 3)
    experiences = extract_experiences(nodes)
    skills = extract_skills(execs, min_support=min_support)
    out = {
        "experiences": [e.to_dict() for e in experiences],
        "skills": [s.to_dict() for s in skills],
        "experience_count": len(experiences),
        "skill_count": len(skills),
    }
    print(json.dumps(out, indent=2))


def _build_graph(spec: dict) -> SkillGraph:
    g = SkillGraph()
    for s in spec.get("skills", []):
        g.add(s["skill_id"], s.get("definition", {}))
        for rec in s.get("executions", []):
            g.learn(s["skill_id"], rec.get("task", {}), rec["outcome"], rec.get("error"))
    return g


def cmd_route(args):
    with open(args.path, encoding="utf-8") as f:
        spec = json.load(f)
    g = _build_graph(spec)
    task = spec["task"]
    chosen = g.route(task)
    task_tokens = set(t for t in task.get("description", "").lower().split())
    print("=" * 70)
    print(f"Routing task pattern={task.get('pattern')!r}: {task.get('description')!r}")
    print("=" * 70)
    print(f"{'skill_id':<24}{'similarity':>12}{'success@pattern':>18}")
    for sid, node in g.skills.items():
        sim = g._similarity(node, task_tokens)  # display only
        print(f"{sid:<24}{sim:>12}{node.success_rate_for(task.get('pattern')):>18.3f}")
    print("-" * 70)
    print(f"routed -> {chosen.skill_id if chosen else None}")


def cmd_amendify(args):
    with open(args.path, encoding="utf-8") as f:
        spec = json.load(f)
    node = SkillNode(spec["skill_id"], spec.get("definition", {}))
    for rec in spec.get("executions", []):
        node.observe(rec.get("task", {}), rec["outcome"], rec.get("error"))
    before_version = node.version
    before_hash = node.content_hash
    before_rate = node.success_rate
    amended = node.amendify(failure_threshold=spec.get("failure_threshold", 0.6))
    print(json.dumps(
        {
            "skill_id": node.skill_id,
            "success_rate": round(before_rate, 4),
            "amended": amended,
            "version_before": before_version,
            "version_after": node.version,
            "hash_before": before_hash[:16],
            "hash_after": node.content_hash[:16],
            "hash_changed": before_hash != node.content_hash,
        },
        indent=2,
    ))


def cmd_scenario(args):
    if args.name != "devops-skill":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps self-improving skill routing (canary vs general deployment)")
    print("AWS account 123456789012 - checkout-service pipeline")
    print("=" * 70)
    g = SkillGraph()
    # General skill: rich in deployment/canary description tokens (high similarity).
    g.add("deployment", {
        "name": "deployment",
        "description": "standard deployment rollout for any service including "
                       "canary deployment shift traffic to new version strategies",
        "steps": ["freeze pipeline", "apply manifest", "watch health"],
    })
    # Specialized skill: fewer overlapping tokens, but the real canary expert.
    g.add("canary-deployment", {
        "name": "canary-deployment",
        "description": "progressive gradual ramp expert with error-rate rollback",
        "steps": ["route 5 percent", "compare error rate", "ramp or roll back"],
    })

    canary_task = {"pattern": "canary", "task_type": "deployment_diagnosis"}
    # General skill on canary tasks: 40% failure (10 runs, 4 failures) -> 0.60.
    for i in range(6):
        g.learn("deployment", canary_task, "success")
    for i in range(4):
        g.learn("deployment", canary_task, "failure", error="canary threshold ignored")
    # Canary skill on canary tasks: mostly successful (8 runs, 1 failure) -> 0.875.
    for i in range(7):
        g.learn("canary-deployment", canary_task, "success")
    g.learn("canary-deployment", canary_task, "failure", error="metrics lag")

    task = {
        "pattern": "canary",
        "description": "run a canary deployment on order-service, shift traffic to new version",
        "task_type": "deployment_diagnosis",
    }
    task_tokens = set(t for t in task["description"].lower().split())
    print(f"{'skill_id':<22}{'similarity':>12}{'success@canary':>16}")
    for sid, node in g.skills.items():
        sim = g._similarity(node, task_tokens)
        print(f"{sid:<22}{sim:>12}{node.success_rate_for('canary'):>16.3f}")
    chosen = g.route(task)
    print("-" * 70)
    print(f"routed -> {chosen.skill_id if chosen else None}")
    print("The general 'deployment' skill has higher description similarity, but")
    print("route() picks 'canary-deployment' on demonstrated success, not name match.")
    assert chosen is not None and chosen.skill_id == "canary-deployment"


def cmd_benchmark(args):
    from lib import extract_experiences as _ee
    failures = []

    # Gate 1: extract_experiences yields one experience per diverged node.
    nodes = [
        {"id": "n1", "task_type": "deploy", "action": "apply v3.3.0", "context": "stripe-python",
         "outcome": "success", "caused_task_failure": False, "neighbors": []},          # not diverged
        {"id": "n2", "task_type": "deploy", "action": "set timeout 10s", "context": "gateway",
         "outcome": "failure", "caused_task_failure": True, "neighbors": ["n1"]},        # diverged (failure)
        {"id": "n3", "task_type": "deploy", "action": "retry with jq", "context": "malformed json",
         "outcome": "recovered", "caused_task_failure": False, "neighbors": ["n2"]},     # diverged (surprise)
    ]
    exps = extract_experiences(nodes)
    if len(exps) != 2:
        failures.append(f"expected 2 experiences from 2 diverged nodes, got {len(exps)}")
    if {e.source_node_id for e in exps} != {"n2", "n3"}:
        failures.append("wrong nodes produced experiences")
    if not any(e.outcome == "failure" for e in exps) or not any(e.outcome == "success" for e in exps):
        failures.append("experience outcome not derived from caused_task_failure")

    # Gate 2: extract_skills needs >= min_support common paths.
    two = [
        {"id": "e1", "task_type": "pool", "path": ["changelog", "kg query", "sizing"],
         "preconditions": ["prod"]},
        {"id": "e2", "task_type": "pool", "path": ["changelog", "kg query", "sizing"],
         "preconditions": ["prod"]},
    ]
    if extract_skills(two, min_support=3):
        failures.append("2 executions should NOT yield a skill at min_support=3")
    three = two + [
        {"id": "e3", "task_type": "pool", "path": ["changelog", "kg query", "sizing"],
         "preconditions": ["prod", "peak"]},
    ]
    skills = extract_skills(three, min_support=3)
    if len(skills) != 1:
        failures.append(f"3 shared-path executions should yield 1 skill, got {len(skills)}")
    elif skills[0].steps != ["changelog", "kg query", "sizing"]:
        failures.append("extracted skill steps wrong")
    elif skills[0].preconditions != ["prod"]:
        failures.append(f"preconditions should be the common intersection, got {skills[0].preconditions}")

    # Gate 3: SkillNode.success_rate computes correctly.
    n = SkillNode("s", {"name": "s", "description": "x"})
    if n.success_rate != 0.0:
        failures.append("empty skill success_rate should be 0.0")
    for _ in range(3):
        n.observe({"pattern": "p"}, "success")
    n.observe({"pattern": "p"}, "failure", error="boom")
    if abs(n.success_rate - 0.75) > 1e-9:
        failures.append(f"success_rate should be 0.75, got {n.success_rate}")

    # Gate 4: amendify fires only below 0.6, bumps version + changes content_hash.
    healthy = SkillNode("ok", {"name": "ok", "description": "d"})
    for _ in range(9):
        healthy.observe({"pattern": "p"}, "success")
    healthy.observe({"pattern": "p"}, "failure", error="e")   # 0.9
    if healthy.amendify() is not False:
        failures.append("amendify should NOT fire above 0.6")
    if healthy.version != 1:
        failures.append("healthy skill version should stay 1")

    sick = SkillNode("bad", {"name": "bad", "description": "d"})
    for _ in range(4):
        sick.observe({"pattern": "p"}, "success")
    for _ in range(6):
        sick.observe({"pattern": "p"}, "failure", error="timeout ignored")   # 0.4
    h0, v0 = sick.content_hash, sick.version
    if sick.amendify() is not True:
        failures.append("amendify should fire below 0.6 with error evidence")
    if sick.version != v0 + 1:
        failures.append("amendify should bump version")
    if sick.content_hash == h0:
        failures.append("amendify should change content_hash")

    # Gate 4b: amendment rolls back when validation fails (no error evidence).
    noevidence = SkillNode("rb", {"name": "rb", "description": "d"})
    for _ in range(6):
        noevidence.observe({"pattern": "p"}, "failure", error=None)  # 0.0, but no error text
    hb = noevidence.content_hash
    if noevidence.amendify() is not False:
        failures.append("amendify should roll back when validation fails")
    if noevidence.version != 1 or noevidence.content_hash != hb:
        failures.append("rolled-back amendify must not mutate version/hash")

    # Gate 5: route ranks by success_rate not similarity (canary vs general).
    g = SkillGraph()
    # General skill is deliberately packed with the task's tokens (high similarity).
    g.add("deployment", {"name": "deployment",
                         "description": "canary deployment rollout shift traffic to new version "
                                        "for any service"})
    # Specialist skill shares fewer task tokens but is the real canary expert.
    g.add("canary-deployment", {"name": "canary-deployment",
                                "description": "progressive gradual ramp expert"})
    ct = {"pattern": "canary"}
    for _ in range(6):
        g.learn("deployment", ct, "success")
    for _ in range(4):
        g.learn("deployment", ct, "failure", error="x")            # 0.60
    for _ in range(7):
        g.learn("canary-deployment", ct, "success")
    g.learn("canary-deployment", ct, "failure", error="x")         # 0.875
    task = {"pattern": "canary",
            "description": "run a canary deployment shift traffic to new version"}
    dep_sim = g._similarity(g.skills["deployment"], set(task["description"].lower().split()))
    can_sim = g._similarity(g.skills["canary-deployment"], set(task["description"].lower().split()))
    chosen = g.route(task)
    if chosen is None or chosen.skill_id != "canary-deployment":
        failures.append(f"route should pick canary by success_rate, got {chosen and chosen.skill_id}")
    if dep_sim < can_sim:
        failures.append("scenario invalid: general skill must not have lower similarity")

    # Gate 6: flag_stale_skills flags a sub-60% skill over recent window.
    stale = SkillNode("stale", {"name": "stale", "description": "d"})
    for _ in range(4):
        stale.observe({"pattern": "p"}, "success")
    for _ in range(6):
        stale.observe({"pattern": "p"}, "failure", error="e")      # recent 10 -> 0.4
    fresh = SkillNode("fresh", {"name": "fresh", "description": "d"})
    for _ in range(9):
        fresh.observe({"pattern": "p"}, "success")
    fresh.observe({"pattern": "p"}, "failure", error="e")          # 0.9
    flagged = flag_stale_skills([stale, fresh], recent=10, floor=0.6)
    if flagged != ["stale"]:
        failures.append(f"flag_stale_skills should flag ['stale'], got {flagged}")

    # Gate 7: retire_experiences half-weights a >90-day experience.
    from datetime import datetime, timezone
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    base_ord = base.toordinal()
    old_exp = AgentExperience("t", "a", "c", "success", "l", "old", base.isoformat())
    new_exp = AgentExperience("t", "a", "c", "success", "l", "new", base.isoformat())
    retired = retire_experiences([old_exp], now_days=base_ord + 91)
    kept = retire_experiences([new_exp], now_days=base_ord + 10)
    if retired[0]["weight"] != 0.5 or not retired[0]["half_weight"]:
        failures.append("experience older than 90 days should be half-weight")
    if kept[0]["weight"] != 1.0:
        failures.append("experience within 90 days should be full-weight")

    # Gate 8: cognify extracts trigger phrases + complexity.
    g2 = SkillGraph()
    g2.add("diag", {"name": "diag", "description": "diagnose connection pool exhaustion",
                    "steps": ["a", "b", "c", "d", "e", "f"]})
    cog = g2.cognify("diag")
    if cog["complexity"] != "high" or not cog["trigger_phrases"]:
        failures.append(f"cognify should report high complexity + trigger phrases, got {cog}")

    total = 8
    passed = total - len(failures)
    print("=" * 70)
    print(f"xskill-self-improving-object benchmark - {passed}/{total} passed")
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

    p_ext = sub.add_parser("extract", help="Extract experiences + skills from a trace file")
    p_ext.add_argument("--path", required=True, help="JSON with execution_nodes + successful_executions")
    p_ext.set_defaults(func=cmd_extract)

    p_route = sub.add_parser("route", help="Route a task to a skill by demonstrated success")
    p_route.add_argument("--path", required=True, help="JSON with a skills list + a task")
    p_route.set_defaults(func=cmd_route)

    p_amend = sub.add_parser("amendify", help="Run amendify() on a skill node spec")
    p_amend.add_argument("--path", required=True, help="JSON with skill_id + definition + executions")
    p_amend.set_defaults(func=cmd_amendify)

    p_scen = sub.add_parser("scenario", help="Run a worked scenario (devops-skill)")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
