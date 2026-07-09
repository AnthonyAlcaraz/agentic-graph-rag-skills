#!/usr/bin/env python3
"""kv-cache-latency-budgeter CLI — concurrency + latency budgeting for a fleet.

Invocations:
    kv-cache-latency-budgeter --help
    kv-cache-latency-budgeter concurrency --gpu 80 --weights 16 --peak-kv 4
    kv-cache-latency-budgeter kv-compress --gpu 80 --weights 16 --peak-kv 4 --kv-factor 2
    kv-cache-latency-budgeter memento
    kv-cache-latency-budgeter speedup --algo betweenness_centrality --cpu-seconds 35
    kv-cache-latency-budgeter budget
    kv-cache-latency-budgeter pipeline --slm-calls 5 --graph-ops 1 --parallel 2
    kv-cache-latency-budgeter benchmark

Every Process step in SKILL.md maps to a subcommand.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lib  # noqa: E402

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "kv-cache-latency-budgeter (Ch8 — Hardware Acceleration)"
    text = SKILL_MD.read_text(encoding="utf-8")
    desc, in_desc, fm, in_fm = [], False, 0, False
    for line in text.splitlines():
        if line.strip() == "---":
            fm += 1
            in_fm = fm == 1
            if fm == 2:
                break
            continue
        if not in_fm:
            continue
        if line.startswith("description:"):
            in_desc = True
            continue
        if in_desc:
            if line and not line[0].isspace():
                in_desc = False
                continue
            desc.append(line.strip())
    return " ".join(d for d in desc if d) or "kv-cache-latency-budgeter"


def cmd_concurrency(args):
    n = lib.kv_bound_concurrency(args.gpu, args.weights, args.peak_kv)
    print(json.dumps({
        "gpu_memory_gb": args.gpu,
        "model_weights_gb": args.weights,
        "peak_kv_per_user_gb": args.peak_kv,
        "concurrent_users": n,
        "note": "Peak KV per active user, not model size, is the binding "
                "constraint (Ch8).",
    }, indent=2))


def cmd_kv_compress(args):
    print(json.dumps(lib.weight_quant_vs_kv_compression(
        args.gpu, args.weights, args.peak_kv,
        weight_quant_factor=args.weight_factor, kv_compression_factor=args.kv_factor,
    ), indent=2))


def cmd_memento(args):
    print(json.dumps(lib.memento_note(), indent=2))


def cmd_speedup(args):
    out = lib.estimate_gpu_time(args.cpu_seconds, args.algo)
    out["blast_radius_reference"] = lib.blast_radius_report()
    print(json.dumps(out, indent=2))


def cmd_budget(args):
    print(json.dumps(lib.LATENCY_BUDGET, indent=2))


def cmd_pipeline(args):
    print(json.dumps(lib.budget_pipeline(args.slm_calls, args.graph_ops, args.parallel), indent=2))


def cmd_benchmark(args):
    failures = []

    # 1: concurrency bound by KV, not model size — small weights, large KV -> few users.
    if lib.kv_bound_concurrency(80, 6, 10) > 8:
        failures.append("large per-user KV should bound concurrency to a small number")

    # 2: KV compression beats weight quantization for concurrency (book claim).
    cmp = lib.weight_quant_vs_kv_compression(80, 16, 8, weight_quant_factor=2, kv_compression_factor=2)
    if cmp["verdict"] != "kv_compression":
        failures.append("KV compression should beat weight quantization for concurrency")
    if cmp["kv_compression_gain"] <= cmp["weight_quant_gain"]:
        failures.append("kv_compression_gain should exceed weight_quant_gain")

    # 3: quantizing weights does not move the ceiling much when KV dominates.
    if cmp["after_weight_quant"] - cmp["baseline_concurrency"] > cmp["kv_compression_gain"]:
        failures.append("weight quant should not out-gain KV compression when KV dominates")

    # 4: MEMENTO note carries the 228,000-trace figure and does NOT fabricate the factor.
    m = lib.memento_note()
    if "228,000" not in m["training"]:
        failures.append("MEMENTO note must cite the 228,000-trace fine-tune")
    if m["peak_kv_reduction_factor"] != "measured (redacted in source)":
        failures.append("MEMENTO reduction factor must be caller-measured, not fabricated")

    # 5: cuGraph speedups match the book (137 pagerank, 485 betweenness, 125 louvain).
    if lib.CUGRAPH_SPEEDUPS["pagerank"]["speedup"] != 137:
        failures.append("pagerank speedup drifted from 137x")
    if lib.CUGRAPH_SPEEDUPS["betweenness_centrality"]["speedup"] != 485:
        failures.append("betweenness speedup drifted from 485x")

    # 6: LiveJournal betweenness (7 min = 420 s) -> ~5 s under 485x; a 35 s CPU
    #    op lands sub-100ms.
    est = lib.estimate_gpu_time(35, "betweenness_centrality")
    if est["gpu_ms"] >= 100:
        failures.append(f"35s @ 485x should be sub-100ms, got {est['gpu_ms']}ms")

    # 7: latency budget ranges match the book.
    lb = lib.LATENCY_BUDGET
    if lb["graph_traversal_ms"] != (5, 50) or lb["slm_inference_ms"] != (50, 200):
        failures.append("latency budget component ranges drifted from the book")
    if lb["low_latency_target_ms"] != 100 or lb["ultra_low_latency_target_ms"] != 30:
        failures.append("latency targets drifted (sub-100ms / sub-30ms)")

    # 8: the DevOps 5-call pipeline lands within the 2s target with parallelism.
    bp = lib.budget_pipeline(5, 1, parallel_factor=2.0)
    if not bp["within_2s_target"]:
        failures.append(f"5-call pipeline should be within 2s, got {bp['estimated_ms']}")

    total = 8
    print("=" * 70)
    print(f"kv-cache-latency-budgeter benchmark — {total - len(failures)}/{total} passed")
    print(f"  KV-vs-weight verdict: {cmp['verdict']} "
          f"(kv gain {cmp['kv_compression_gain']} vs weight gain {cmp['weight_quant_gain']})")
    print(f"  blast radius 35s CPU -> {est['gpu_ms']}ms GPU (betweenness 485x)")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All gates passed.")
    sys.exit(0)


def main():
    p = argparse.ArgumentParser(prog="kv-cache-latency-budgeter", description=_skill_description())
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("concurrency", help="KV-bound concurrent users for a GPU")
    pc.add_argument("--gpu", type=float, default=lib.H100_MEMORY_GB)
    pc.add_argument("--weights", type=float, required=True)
    pc.add_argument("--peak-kv", type=float, required=True)
    pc.set_defaults(func=cmd_concurrency)

    pk = sub.add_parser("kv-compress", help="Weight-quant vs KV-compression concurrency gain")
    pk.add_argument("--gpu", type=float, default=lib.H100_MEMORY_GB)
    pk.add_argument("--weights", type=float, required=True)
    pk.add_argument("--peak-kv", type=float, required=True)
    pk.add_argument("--weight-factor", type=float, default=2.0)
    pk.add_argument("--kv-factor", type=float, default=2.0)
    pk.set_defaults(func=cmd_kv_compress)

    sub.add_parser("memento", help="MEMENTO KV-bounding recipe (measure-first tip)").set_defaults(func=cmd_memento)

    ps = sub.add_parser("speedup", help="Estimate GPU time from a CPU baseline (cuGraph)")
    ps.add_argument("--algo", choices=sorted(lib.CUGRAPH_SPEEDUPS), default="pagerank")
    ps.add_argument("--cpu-seconds", type=float, required=True)
    ps.set_defaults(func=cmd_speedup)

    sub.add_parser("budget", help="Print the latency budget table + targets").set_defaults(func=cmd_budget)

    pp = sub.add_parser("pipeline", help="Estimate end-to-end pipeline latency vs the 2s target")
    pp.add_argument("--slm-calls", type=int, default=5)
    pp.add_argument("--graph-ops", type=int, default=1)
    pp.add_argument("--parallel", type=float, default=1.0)
    pp.set_defaults(func=cmd_pipeline)

    sub.add_parser("benchmark", help="Verification gate battery").set_defaults(func=cmd_benchmark)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
