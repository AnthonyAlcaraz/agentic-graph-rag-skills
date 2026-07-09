"""
Harness node splitter (Ch2 — "Defining the harness" + "Splitting a workflow
into nodes").

The horizontal workflow graph says WHAT the agent should do; the harness
executes it. The harness is a runtime with six surfaces:

  1. holds the workflow graph as inspectable state
  2. advances the graph under a named policy (sequential / parallel / dynamic)
  3. exposes a typed TOOL REGISTRY through which nodes invoke side effects
  4. mediates a typed MEMORY INTERFACE (reads/writes to the vertical graph)
  5. enforces a SCHEMA VALIDATOR constraining each node's output to its
     downstream neighbor's input contract
  6. maintains an append-only OBSERVATION RECORD of every invocation

This module implements the node-splitting design rule the chapter states:

    "Nodes differ by tool surface, not by prompt."

RedAI (Kyle Polley, April 2026) is the sharp public example: the SCANNER node
holds a filesystem and threat-models code (optimized for recall); the VALIDATOR
node holds a browser driver, an iOS simulator, a network stack, and a scripting
runtime, and drives each finding into a live environment. Swap the prompts and
nothing changes — the role lives in the tool surface. The chapter's Tip:

    "Before you add a node to the workflow graph, list the tools it will call.
    If the list overlaps more than 80% with an existing node, you have a prompt
    variation of that node rather than a new role. Merge them and vary the
    prompt. If the tool lists differ substantially, split."

So this skill takes candidate operations (each with a declared tool set) and
applies the tool-overlap rule to decide merge-vs-split, then emits the
constrained per-node context scope the harness needs (tool surface + memory
access + input/output contract).

Pure Python, stdlib only.

Production swap: `tool_overlap` uses symmetric Jaccard over declared tool names.
In production a harness derives the true tool surface from the typed tool
registry (surface 3) and may weight tools by cost/risk. The merge/split
CONTRACT (>= threshold overlap => merge, else split) is the stable seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Set

# The chapter's four horizontal-node responsibilities, plus the two extra
# labels used in Example 2-3 (retrieval, generation). Validation is included
# because the harness enforces a schema validator per node.
NODE_TYPES = (
    "reasoning",     # interpret alerts, evaluate evidence, identify patterns
    "retrieval",     # query the vertical knowledge graph for context
    "execution",     # call APIs / run diagnostics (a.k.a. tool_call)
    "decision",      # branch to different next steps
    "validation",    # check output conforms to a schema / evidence / policy
    "generation",    # produce a structured artifact (e.g. the incident report)
)

# The chapter's tool-overlap threshold. "Overlaps more than 80% => merge."
DEFAULT_OVERLAP_THRESHOLD = 0.8


@dataclass
class Operation:
    """A candidate workflow operation before split/merge is decided."""
    id: str
    task: str = ""
    node_type: str = "reasoning"
    tools: List[str] = field(default_factory=list)
    reads: List[str] = field(default_factory=list)    # memory slices it reads
    writes: List[str] = field(default_factory=list)   # memory slices it writes
    input_contract: str = ""                           # expected input schema
    output_schema: str = ""                            # promised output schema

    def tool_set(self) -> Set[str]:
        return {t.strip() for t in self.tools if t.strip()}


@dataclass
class Node:
    """A workflow node after split/merge — a constrained context scope."""
    id: str
    node_type: str
    tools: List[str]
    tasks: List[str]                 # >1 => merged; the prompt varies at input
    reads: List[str]
    writes: List[str]
    input_contract: str
    output_schema: str
    merged_from: List[str] = field(default_factory=list)

    @property
    def is_merged(self) -> bool:
        return len(self.merged_from) > 1


@dataclass
class SplitResult:
    nodes: List[Node]
    decisions: List[dict]            # per-pair merge/split rationale
    threshold: float


def tool_overlap(a: Set[str], b: Set[str]) -> float:
    """
    Symmetric Jaccard overlap of two tool sets: |A ∩ B| / |A ∪ B|.

    Two nodes with identical tool surfaces score 1.0 (pure prompt variation —
    merge). Two nodes with disjoint tool surfaces score 0.0 (distinct roles —
    split). The RedAI scanner (filesystem) vs validator (browser/ios/network)
    pair scores 0.0.

    Edge case: two tool-LESS nodes (both empty sets) score 0.0, NOT 1.0. The
    chapter's rule keys entirely on the TOOL LIST ("list the tools it will
    call"); a node that calls no tools has no tool surface to distinguish it, so
    its role lives in its prompt and its position in the DAG, not in tools. That
    is exactly why Example 2-3 keeps `classify` (severity) and `analyze` (root
    cause) as separate reasoning nodes even though both call no tools. Default
    tool-less nodes to split; merge them only by an explicit caller decision.
    """
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def split_nodes(
    operations: Sequence[Operation],
    threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> SplitResult:
    """
    Apply the tool-surface rule to a list of candidate operations.

    Greedy single pass: each operation either merges into an existing node
    whose tool overlap is >= threshold AND shares its node_type, or starts a
    new node. Merging unions the tool sets and appends the task as a prompt
    variant (the merged node varies its prompt at the input, per the Tip).

    node_type is part of the merge key: a reasoning node and an execution node
    that happen to share a tool are still different roles. The chapter's rule is
    tool-surface-first, but a retrieval node and a generation node are not the
    same role even at 100% tool overlap — they promise different outputs to the
    schema validator (harness surface 5).
    """
    nodes: List[Node] = []
    decisions: List[dict] = []

    for op in operations:
        op_tools = op.tool_set()
        target: Node | None = None
        for node in nodes:
            if node.node_type != op.node_type:
                continue
            ov = tool_overlap(op_tools, set(node.tools))
            decisions.append({
                "candidate": op.id,
                "compared_to": node.id,
                "overlap": round(ov, 3),
                "action": "merge" if ov >= threshold else "consider-split",
            })
            if ov >= threshold:
                target = node
                break
        if target is None:
            nodes.append(Node(
                id=op.id,
                node_type=op.node_type,
                tools=sorted(op_tools),
                tasks=[op.task] if op.task else [],
                reads=list(op.reads),
                writes=list(op.writes),
                input_contract=op.input_contract,
                output_schema=op.output_schema,
                merged_from=[op.id],
            ))
        else:
            target.tools = sorted(set(target.tools) | op_tools)
            if op.task:
                target.tasks.append(op.task)
            target.reads = sorted(set(target.reads) | set(op.reads))
            target.writes = sorted(set(target.writes) | set(op.writes))
            target.merged_from.append(op.id)
            # Downstream contract widens to cover both promises.
            if op.output_schema and op.output_schema not in target.output_schema:
                target.output_schema = (
                    f"{target.output_schema} | {op.output_schema}"
                    if target.output_schema else op.output_schema
                )

    return SplitResult(nodes=nodes, decisions=decisions, threshold=threshold)


def node_scope(node: Node) -> Dict[str, object]:
    """
    The constrained per-node context scope the harness enforces (surfaces 3-5):
    the tool surface it may invoke, the memory slices it reads/writes, and the
    input/output contract the schema validator holds it to.

    This is what "each node has a focused responsibility" means concretely: a
    node sees only its own tools and its own memory slice, not the whole
    registry or the whole graph.
    """
    return {
        "id": node.id,
        "node_type": node.node_type,
        "tool_surface": node.tools,
        "memory_reads": node.reads,
        "memory_writes": node.writes,
        "input_contract": node.input_contract,
        "output_schema": node.output_schema,
        "prompt_variants": node.tasks,
        "is_merged": node.is_merged,
    }


def audit_operation(
    operation: Operation,
    existing: Sequence[Node],
    threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> Dict[str, object]:
    """
    The Tip as a pre-add gate: before adding a node, list its tools and compare
    against existing nodes. Returns the best match and a verdict.

    verdict == "merge" means the operation is a prompt variation of an existing
    node (overlap >= threshold, same type). verdict == "split" means the tool
    surface is distinct enough to be a new role.
    """
    op_tools = operation.tool_set()
    best_id = None
    best_ov = -1.0
    for node in existing:
        if node.node_type != operation.node_type:
            continue
        ov = tool_overlap(op_tools, set(node.tools))
        if ov > best_ov:
            best_ov, best_id = ov, node.id
    verdict = "merge" if best_ov >= threshold else "split"
    return {
        "operation": operation.id,
        "best_match": best_id,
        "best_overlap": round(best_ov, 3) if best_ov >= 0 else None,
        "threshold": threshold,
        "verdict": verdict,
        "reason": (
            f"tool overlap {best_ov:.2f} >= {threshold} with {best_id!r}: "
            "prompt variation, merge and vary the prompt at the input"
            if verdict == "merge" and best_id is not None
            else "distinct tool surface: this is a new role, split"
        ),
    }


def operations_from_dicts(rows: List[dict]) -> List[Operation]:
    """Build Operation objects from JSON-shaped rows."""
    ops: List[Operation] = []
    for r in rows:
        ops.append(Operation(
            id=r["id"],
            task=r.get("task", ""),
            node_type=r.get("node_type", "reasoning"),
            tools=list(r.get("tools", [])),
            reads=list(r.get("reads", [])),
            writes=list(r.get("writes", [])),
            input_contract=r.get("input_contract", ""),
            output_schema=r.get("output_schema", ""),
        ))
    return ops
