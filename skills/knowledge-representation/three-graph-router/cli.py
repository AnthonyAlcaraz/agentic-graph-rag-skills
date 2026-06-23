#!/usr/bin/env python3
"""three-graph-router CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    Record, route, link_subject_to_domain, cross_graph_query_path,
    DEFAULT_THRESHOLD, GRAPHS,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "three-graph-router (Ch3)"
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
    return " ".join(d for d in desc if d) or "three-graph-router"


def cmd_route(args):
    with open(args.record_path) as f:
        spec = json.load(f)
    rec = Record(
        payload=spec.get("payload", {}),
        origin=spec["origin"],
        entity_resolved=spec.get("entity_resolved", False),
        has_provenance=spec.get("has_provenance", False),
        confidence=spec.get("confidence"),
    )
    try:
        print(json.dumps(route(rec), indent=2))
    except ValueError as e:
        print(json.dumps({"error": str(e)}, indent=2))
        sys.exit(2)


def cmd_link(args):
    with open(args.candidates_path) as f:
        candidates = json.load(f)
    corr = link_subject_to_domain(args.subject, candidates, threshold=args.threshold)
    if corr is None:
        print(json.dumps({"linked": False, "reason": "no candidates"}, indent=2))
        return
    print(json.dumps(corr.__dict__, indent=2))


def cmd_path(args):
    print(json.dumps({
        "from": args.start, "to": args.target,
        "edge_path": cross_graph_query_path(args.start, args.target),
    }, indent=2))


def cmd_scenario(args):
    if args.name != "stockholm-chair":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("Customer review mentions 'the Stockholm chair' (Ch3 worked example)")
    print("=" * 70)

    # 1) Domain: the canonical product catalog (structured, entity-resolved).
    domain_rec = Record(payload={"product_id": "PROD_12345", "name": "Stockholm Chair"},
                        origin="structured", entity_resolved=True)
    print("\n[1] Catalog row -> ", route(domain_rec)["graph"])

    # 2) Lexical: the raw review text with provenance.
    lexical_rec = Record(payload={"text": "the Stockholm chair wobbles"},
                        origin="raw_text", has_provenance=True)
    print("[2] Review chunk -> ", route(lexical_rec)["graph"])

    # 3) Subject: the LLM-extracted product mention with confidence.
    subject_rec = Record(payload={"name": "the Stockholm chair"},
                        origin="extraction", confidence=0.0)
    print("[3] Extracted entity -> ", route(subject_rec)["graph"])

    # 4) Entity resolution: link subject -> domain via CORRESPONDS_TO.
    print("\n[4] CORRESPONDS_TO linkage (threshold 0.85):")
    corr = link_subject_to_domain(
        "the Stockholm chair",
        {"PROD_12345": "Stockholm Chair", "PROD_99999": "Malmo Sofa"},
        threshold=DEFAULT_THRESHOLD,
    )
    print(json.dumps(corr.__dict__, indent=2))

    # 5) Cross-graph query path.
    print("\n[5] Cross-graph query path domain -> lexical:")
    print(json.dumps(cross_graph_query_path("domain", "lexical"), indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: structured + resolved -> domain.
    r = route(Record({}, "structured", entity_resolved=True))
    if r["graph"] != "domain" or r["label_suffix"] != "Domain":
        failures.append("structured+resolved should route to domain")

    # Test 2: raw_text + provenance -> lexical.
    r = route(Record({}, "raw_text", has_provenance=True))
    if r["graph"] != "lexical":
        failures.append("raw_text+provenance should route to lexical")

    # Test 3: extraction + confidence -> subject, requires resolution.
    r = route(Record({}, "extraction", confidence=0.7))
    if r["graph"] != "subject" or not r["requires_resolution"]:
        failures.append("extraction should route to subject + require resolution")

    # Test 4: raw_text WITHOUT provenance must raise (no silent lexical insert).
    try:
        route(Record({}, "raw_text", has_provenance=False))
        failures.append("raw_text w/o provenance should raise")
    except ValueError:
        pass

    # Test 5: extraction WITHOUT confidence must raise.
    try:
        route(Record({}, "extraction", confidence=None))
        failures.append("extraction w/o confidence should raise")
    except ValueError:
        pass

    # Test 6: extraction marked entity_resolved must raise (no domain contamination).
    try:
        route(Record({}, "extraction", confidence=0.9, entity_resolved=True))
        failures.append("extraction marked resolved should NOT route to domain")
    except ValueError:
        pass

    # Test 7: unknown origin raises.
    try:
        route(Record({}, "spreadsheet"))
        failures.append("unknown origin should raise")
    except ValueError:
        pass

    # Test 8: linkage above threshold links; below does not.
    corr = link_subject_to_domain("Stockholm Chair",
                                  {"PROD_12345": "Stockholm Chair"}, threshold=0.85)
    if not corr.linked:
        failures.append("identical name should link above 0.85")
    corr2 = link_subject_to_domain("Stockholm Chair",
                                   {"PROD_99999": "Malmo Sofa"}, threshold=0.85)
    if corr2.linked:
        failures.append("dissimilar name should NOT link")

    # Test 9: best candidate is chosen among several.
    corr3 = link_subject_to_domain(
        "the stockholm chair",
        {"PROD_1": "Malmo Sofa", "PROD_2": "Stockholm Chair", "PROD_3": "Oslo Desk"},
        threshold=0.5,
    )
    if corr3.domain_id != "PROD_2":
        failures.append(f"should pick closest match, got {corr3.domain_id}")

    # Test 10: cross-graph path domain->lexical traverses CORRESPONDS_TO then EXTRACTED_FROM.
    path = cross_graph_query_path("domain", "lexical")
    if path != ["CORRESPONDS_TO", "EXTRACTED_FROM"]:
        failures.append(f"domain->lexical path wrong: {path}")
    if cross_graph_query_path("domain", "domain") != []:
        failures.append("same-graph path should be empty")

    total = 10
    print("=" * 70)
    print(f"three-graph-router benchmark - {total - len(failures)}/{total} passed")
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

    p_route = sub.add_parser("route", help="Route a record JSON to a graph")
    p_route.add_argument("--record-path", required=True)
    p_route.set_defaults(func=cmd_route)

    p_link = sub.add_parser("link", help="CORRESPONDS_TO link subject -> domain")
    p_link.add_argument("--subject", required=True)
    p_link.add_argument("--candidates-path", required=True, help="JSON {domain_id: name}")
    p_link.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    p_link.set_defaults(func=cmd_link)

    p_path = sub.add_parser("path", help="Cross-graph query edge path")
    p_path.add_argument("--start", required=True, choices=GRAPHS)
    p_path.add_argument("--target", required=True, choices=GRAPHS)
    p_path.set_defaults(func=cmd_path)

    p_scen = sub.add_parser("scenario", help="Worked scenario (stockholm-chair)")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
