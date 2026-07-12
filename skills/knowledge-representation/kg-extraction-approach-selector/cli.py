#!/usr/bin/env python3
"""kg-extraction-approach-selector CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    Profile, score_approaches, recommend_approach, incremental_cost,
    FEATURES, APPROACHES,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "kg-extraction-approach-selector (Ch3)"
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
    return " ".join(d for d in desc if d) or "kg-extraction-approach-selector"


def _profile_from_args(args) -> Profile:
    return Profile(
        source_type=args.source_type,
        incremental=args.incremental,
        document_context_needed=args.document_context,
        schema_stability=args.schema_stability,
        determinism_need=args.determinism_need,
        volume=args.volume,
    )


def cmd_recommend(args):
    profile = _profile_from_args(args)
    print(json.dumps(recommend_approach(profile), indent=2))


def cmd_score(args):
    profile = _profile_from_args(args)
    print(json.dumps(dict(score_approaches(profile)), indent=2))


def cmd_incremental_cost(args):
    print(json.dumps(
        incremental_cost(args.new_docs, args.total_docs, args.approach),
        indent=2))


def cmd_scenario(args):
    if args.name != "growing-infra-telemetry":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("Infra-telemetry KG - unstructured logs, corpus grows daily")
    print("=" * 70)
    # New telemetry documents arrive continuously; re-extracting the whole
    # corpus every day is wasteful, so incremental construction wins.
    profile = Profile(source_type="unstructured", incremental=True,
                      determinism_need=1, volume=5000)
    rec = recommend_approach(profile)
    print(json.dumps(rec, indent=2))
    print("\nIncremental cost of adding 50 docs to a 5000-doc corpus:")
    print(json.dumps(incremental_cost(50, 5000, rec["recommended"]), indent=2))
    print("\nvs a full-rebuild approach (rakg) on the same update:")
    print(json.dumps(incremental_cost(50, 5000, "rakg"), indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: structured source hard-routes to structured DB integration.
    p = Profile(source_type="structured", incremental=True, determinism_need=0)
    if recommend_approach(p)["recommended"] != "structured_db":
        failures.append("structured source should pick structured_db")

    # Test 2: unstructured + growing corpus -> incremental iText2KG.
    p = Profile(source_type="unstructured", incremental=True)
    if recommend_approach(p)["recommended"] != "itext2kg":
        failures.append("unstructured + incremental should pick itext2kg")

    # Test 3: unstructured + whole-document context -> RAKG.
    p = Profile(source_type="unstructured", document_context_needed=True)
    if recommend_approach(p)["recommended"] != "rakg":
        failures.append("unstructured + document context should pick rakg")

    # Test 4: unstructured one-shot -> plain LLM-based extraction.
    p = Profile(source_type="unstructured")
    if recommend_approach(p)["recommended"] != "llm_extraction":
        failures.append("unstructured one-shot should pick llm_extraction")

    # Test 5: mixed source with growth still routes to incremental.
    p = Profile(source_type="mixed", incremental=True)
    if recommend_approach(p)["recommended"] != "itext2kg":
        failures.append("mixed + incremental should pick itext2kg")

    # Test 6: incremental approach processes only the new documents.
    cost = incremental_cost(50, 5000, "itext2kg")
    if cost["docs_processed"] != 50 or cost["docs_reprocessed"] != 0:
        failures.append(f"itext2kg should process only new docs, got {cost['docs_processed']}")

    # Test 7: a full-rebuild approach re-processes the whole corpus.
    cost = incremental_cost(50, 5000, "rakg")
    if cost["docs_processed"] != 5000:
        failures.append(f"rakg should reprocess all docs, got {cost['docs_processed']}")

    # Test 8: incremental savings equal the reprocessing a rebuild would pay.
    cost = incremental_cost(50, 5000, "itext2kg")
    if cost["savings_vs_rebuild"] != 5000 - 50:
        failures.append(f"incremental savings wrong, got {cost['savings_vs_rebuild']}")

    # Test 9: every approach scored, ordered descending, none dropped.
    scored = score_approaches(Profile(source_type="unstructured",
                                      incremental=True, document_context_needed=True,
                                      determinism_need=1))
    if len(scored) != len(APPROACHES):
        failures.append("all approaches must be scored")
    if [s for _, s in scored] != sorted([s for _, s in scored], reverse=True):
        failures.append("scores must be sorted descending")

    # Test 10: feature set is exactly the 5 chapter axes.
    if set(FEATURES) != {"handles_unstructured", "incremental_friendly",
                         "document_level_context", "determinism", "setup_cost"}:
        failures.append("feature set drifted from the 5 chapter axes")

    total = 10
    print("=" * 70)
    print(f"kg-extraction-approach-selector benchmark - {total - len(failures)}/{total} passed")
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

    def add_profile_args(p):
        p.add_argument("--source-type", choices=["structured", "unstructured", "mixed"],
                       default="unstructured")
        p.add_argument("--incremental", action="store_true",
                       help="corpus grows over time; avoid full re-extraction")
        p.add_argument("--document-context", action="store_true",
                       help="relations need whole-document / cross-mention context")
        p.add_argument("--schema-stability", type=int, default=0)
        p.add_argument("--determinism-need", type=int, default=0)
        p.add_argument("--volume", type=int, default=0)

    p_rec = sub.add_parser("recommend", help="Recommend an extraction approach from a source profile")
    add_profile_args(p_rec)
    p_rec.set_defaults(func=cmd_recommend)

    p_score = sub.add_parser("score", help="Score all four approaches from a source profile")
    add_profile_args(p_score)
    p_score.set_defaults(func=cmd_score)

    p_inc = sub.add_parser("incremental-cost", help="Docs re-processed on an update, per approach")
    p_inc.add_argument("--new-docs", type=int, required=True)
    p_inc.add_argument("--total-docs", type=int, required=True)
    p_inc.add_argument("--approach", choices=list(APPROACHES), default="itext2kg")
    p_inc.set_defaults(func=cmd_incremental_cost)

    p_scen = sub.add_parser("scenario", help="Worked scenario (growing-infra-telemetry)")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
