"""CLI for the irreversible-action gate.

--help prints the SKILL.md description (so any harness can discover the skill
from --help); each Process step maps to a subcommand; `benchmark` is the
verification battery.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import (  # noqa: E402
    IRREVERSIBLE,
    REVERSIBLE,
    SEMI_REVERSIBLE,
    Action,
    action_from_spec,
    classify,
    gate,
    prescribe,
    saga,
)


def _skill_description() -> str:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SKILL.md")
    text = open(path, encoding="utf-8").read()
    m = re.search(r"description: \|\n((?:  .*\n)+)", text)
    return "".join(l[2:] for l in m.group(1).splitlines(keepends=True)) if m else ""


def _load(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_classify(args) -> None:
    print(json.dumps(classify(action_from_spec(_load(args.action_spec))), indent=2))


def cmd_prescribe(args) -> None:
    print(json.dumps(prescribe(action_from_spec(_load(args.action_spec))), indent=2))


def cmd_gate(args) -> None:
    action = action_from_spec(_load(args.action_spec))
    result = gate(action, _load(args.facts))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["allowed"] else 3)


def cmd_saga(args) -> None:
    plan = _load(args.plan_spec)
    actions = [action_from_spec(s) for s in plan["actions"]]
    print(json.dumps(saga(actions), indent=2))


def cmd_scenario(args) -> None:
    if args.name != "devops-remediation":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("checkout-service remediation plan, gated before execution")
    print("Fictional AWS account 123456789012")
    print("=" * 70)
    plan = [
        Action("query_cloudwatch_latency", side_effect_scope="none", idempotent=True),
        Action("rollback_db_parameter_group", side_effect_scope="internal",
               compensating_action="reapply_parameter_change",
               preconditions=["rollbackApproved", "lastKnownGoodVersion"]),
        Action("scale_out_ecs_service", side_effect_scope="internal",
               compensating_action="scale_in_ecs_service", idempotent=True),
        Action("delete_stale_connection_pool_snapshot", side_effect_scope="internal",
               data_destructive=True),
        Action("page_oncall_dba", side_effect_scope="external"),
    ]
    for a in plan:
        p = prescribe(a)
        print(f"\n--- {a.name} [{p['class']}] ---")
        print(json.dumps(p, indent=2))
    print("\n--- saga analysis ---")
    print(json.dumps(saga(plan), indent=2))
    print("\nReading: the deletion is the point of no return; the page to the")
    print("on-call is external and irreversible but sits after it (forward")
    print("recovery only). Compensations for the rollback and the scale-out")
    print("are registered before anything destructive runs.")


def cmd_benchmark(args) -> None:
    checks = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    print("irreversible-action-gate benchmark")
    print("-" * 60)

    read = Action("get_metrics", side_effect_scope="none", idempotent=True)
    check("pure read classifies REVERSIBLE", classify(read)["class"] == REVERSIBLE)
    check("pure read retry is safe_retry", prescribe(read)["retry_policy"] == "safe_retry")

    comp = Action("scale_out", side_effect_scope="internal",
                  compensating_action="scale_in")
    check("compensable internal mutation is SEMI_REVERSIBLE",
          classify(comp)["class"] == SEMI_REVERSIBLE)
    check("SEMI_REVERSIBLE requires compensation registration before execute",
          prescribe(comp)["register_compensation_before_execute"] is True)

    delete = Action("delete_snapshot", side_effect_scope="internal",
                    data_destructive=True)
    check("destructive without restore path is IRREVERSIBLE",
          classify(delete)["class"] == IRREVERSIBLE)
    check("IRREVERSIBLE without dry-run requires human approval",
          prescribe(delete)["human_approval_required"] is True)

    delete_dr = Action("delete_snapshot", side_effect_scope="internal",
                       data_destructive=True, supports_dry_run=True)
    check("IRREVERSIBLE with dry-run support prescribes dry-run-first, not approval",
          prescribe(delete_dr)["dry_run_first"] is True
          and prescribe(delete_dr)["human_approval_required"] is False)

    restore = Action("delete_row", side_effect_scope="internal",
                     data_destructive=True, compensating_action="restore_from_backup")
    check("destructive WITH internal restore path is SEMI_REVERSIBLE",
          classify(restore)["class"] == SEMI_REVERSIBLE)

    page = Action("page_oncall", side_effect_scope="external")
    check("uncompensable external effect is IRREVERSIBLE",
          classify(page)["class"] == IRREVERSIBLE)
    check("external destructive delete is IRREVERSIBLE even with named compensation",
          classify(Action("purge_partner_data", side_effect_scope="external",
                          data_destructive=True,
                          compensating_action="ask_partner_nicely"))["class"]
          == IRREVERSIBLE)

    nonidem = Action("create_ticket", side_effect_scope="external",
                     compensating_action="close_ticket")
    p = prescribe(nonidem)
    check("non-idempotent mutation requires an idempotency key",
          p["idempotency_key_required"] is True
          and p["retry_policy"] == "at_least_once_with_idempotency_key")
    check("IRREVERSIBLE prescription escalates decision reads to strong consistency",
          "STRONG" in prescribe(delete)["consistency_note"])

    guarded = Action("rollback_deployment", side_effect_scope="internal",
                     compensating_action="redeploy",
                     preconditions=["rollbackApproved", "lastKnownGoodVersion"])
    check("gate fails closed on missing fact",
          gate(guarded, {"rollbackApproved": True})["allowed"] is False)
    check("gate allows when every precondition holds",
          gate(guarded, {"rollbackApproved": True,
                         "lastKnownGoodVersion": True})["allowed"] is True)

    plan = [read, comp, delete, page,
            Action("update_runbook", side_effect_scope="internal",
                   compensating_action="revert_runbook")]
    s = saga(plan)
    check("PONR is the FIRST irreversible step",
          s["point_of_no_return"]["index"] == 2)
    check("compensation stack covers only pre-PONR steps, in reverse order",
          s["compensation_stack"] == ["scale_in"])
    check("reversible step after PONR raises a reorder flag",
          any("update_runbook" in f for f in s["reorder_flags"]))
    check("bad side_effect_scope raises ValueError", _raises())

    passed = sum(1 for _, ok in checks if ok)
    print("-" * 60)
    print(f"{passed}/{len(checks)} gates passed")
    if passed != len(checks):
        sys.exit(1)
    print("All gates passed.")


def _raises() -> bool:
    try:
        Action("x", side_effect_scope="cosmic")
        return False
    except ValueError:
        return True


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="irreversible-action-gate",
        description=_skill_description(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("classify", help="Step 1: classify an action's reversibility")
    p.add_argument("--action-spec", required=True)
    p.set_defaults(func=cmd_classify)

    p = sub.add_parser("prescribe", help="Step 2: prescribe the delivery contract")
    p.add_argument("--action-spec", required=True)
    p.set_defaults(func=cmd_prescribe)

    p = sub.add_parser("gate", help="Step 3: precondition gate (exit 3 when blocked)")
    p.add_argument("--action-spec", required=True)
    p.add_argument("--facts", required=True)
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("saga", help="Step 4: compensation stack + point of no return")
    p.add_argument("--plan-spec", required=True)
    p.set_defaults(func=cmd_saga)

    p = sub.add_parser("scenario", help="Step 5: checkout-service remediation worked example")
    p.add_argument("name")
    p.set_defaults(func=cmd_scenario)

    p = sub.add_parser("benchmark", help="Step 6: verification battery")
    p.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
