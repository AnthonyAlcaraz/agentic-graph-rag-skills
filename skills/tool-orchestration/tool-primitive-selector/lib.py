"""
Primitive selection (CLI vs MCP vs Skill) for exposing an agent capability,
distilled from Ch6 "Choosing the Right Primitive: CLIs, MCPs, and Skills".

The chapter's central claim: the three primitives are NOT competitors. They
converge at the transport layer while staying distinct at the usage layer, and
a single capability is often exposed as more than one (the Google Workspace CLI
ships a CLI surface, an MCP server mode, AND 100+ skills -- one tool, three
interfaces). So the selector recommends a PRIMARY primitive and, where the
capability warrants it, an `also_expose_as` list -- convergence, not competition.

Each primitive answers a different question and serves a different audience on a
personal-to-enterprise gradient:

  CLI    "how does the agent PERFORM this operation?"  deterministic command
         surface, Unix-pipe composable, self-describing via --help, no model
         needed to invoke. Audience: individual developer in build mode / CI.

  MCP    "how does the agent CONNECT to this service securely?"  model-callable
         tool server with schemas, runtime-discoverable, OAuth + scoped
         per-agent access control via gateways. Audience: team / enterprise /
         unsupervised background agents.

  SKILL  "WHAT should the agent do and in what order?"  encoded judgment /
         procedure the model reads; natural language, no install, works for
         everyone. Audience: the model itself. Skills come first regardless.

Pure Python, stdlib only. No tool runtime required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


PRIMITIVES = ("cli", "mcp", "skill")

# The six feature axes the chapter's taxonomy compares primitives across.
AXES = (
    "deterministic_surface",   # identical inputs -> identical outputs, no model
    "runtime_discoverable",    # agent finds + calls it at runtime with schemas
    "access_control",          # fine-grained per-agent scoping / audit / OAuth
    "encodes_judgment",        # carries how-to / when / in-what-order procedure
    "personal_fit",            # fits the solo / build-mode / single-machine end
    "enterprise_fit",          # fits the many-stakeholder / governed end
)

# Per-primitive score per axis on a 0..3 ordinal scale distilled from the
# "Three primitives, three audiences", "personal-to-enterprise gradient", and
# "per-agent access control" sections. Higher == stronger on that axis.
PRIMITIVE_FEATURE_SCORES: Dict[str, Dict[str, int]] = {
    "cli": {
        "deterministic_surface": 3, "runtime_discoverable": 1,
        "access_control": 1,  # runs through the OS permission model, a blunt
                              # instrument for agent-level scoping
        "encodes_judgment": 0, "personal_fit": 3, "enterprise_fit": 1,
    },
    "mcp": {
        "deterministic_surface": 1, "runtime_discoverable": 3,
        "access_control": 3,  # gateway: fine-grained perms, audit, allowed_tools
        "encodes_judgment": 0, "personal_fit": 1, "enterprise_fit": 3,
    },
    "skill": {
        "deterministic_surface": 0, "runtime_discoverable": 1,
        "access_control": 0, "encodes_judgment": 3,
        "personal_fit": 2, "enterprise_fit": 2,  # skills stay constant across
                                                 # the whole gradient
    },
}


@dataclass
class Capability:
    """A capability to expose to an agent, profiled along the chapter's four
    dimensions (who / when-invoked / access) plus a composability need.

    audience: who runs the workflow and at what scale.
        individual | team | enterprise (the personal-to-enterprise gradient).
    invocation: how the capability is exercised.
        deterministic_command   -> a fixed command surface (favors CLI)
        runtime_agent_discovery  -> agent discovers + calls at runtime (MCP)
        judgment_guidance        -> the value is procedure / when-and-how (SKILL)
    needs_per_agent_access_control: least-privilege scoping per named agent
        (allowed_tools). An MCP-gradient governance concern.
    needs_model_to_invoke: does exercising the capability require a model in the
        loop? False for deterministic scripting/CI surfaces (favors CLI).
    composability_need: 0..3, how much Unix-pipe chaining matters (favors CLI).
    """
    audience: str = "individual"
    invocation: str = "deterministic_command"
    needs_per_agent_access_control: bool = False
    needs_model_to_invoke: bool = False
    composability_need: int = 0

    def validate(self) -> None:
        if self.audience not in ("individual", "team", "enterprise"):
            raise ValueError(f"bad audience: {self.audience}")
        if self.invocation not in (
            "deterministic_command", "runtime_agent_discovery",
            "judgment_guidance",
        ):
            raise ValueError(f"bad invocation: {self.invocation}")
        if not 0 <= int(self.composability_need) <= 3:
            raise ValueError("composability_need must be 0..3")


# Governance weight applied when per-agent access control is required. High
# enough that an enterprise, governed capability tips from CLI to MCP even when
# it is deterministic -- the chapter's CLI-to-MCP shift up the gradient.
_ACCESS_CONTROL_WEIGHT = 4


def _weights(cap: Capability) -> Dict[str, int]:
    """Translate a capability profile into per-axis weights. The invocation
    axis is the primary signal; audience places it on the gradient; access
    control + composability + model-need are the secondary tilts."""
    cap.validate()
    w = {axis: 0 for axis in AXES}

    # Invocation is the primary signal.
    if cap.invocation == "deterministic_command":
        w["deterministic_surface"] += 3
    elif cap.invocation == "runtime_agent_discovery":
        w["runtime_discoverable"] += 3
    elif cap.invocation == "judgment_guidance":
        w["encodes_judgment"] += 3

    # Audience places the capability on the personal-to-enterprise gradient.
    if cap.audience == "individual":
        w["personal_fit"] += 2
    elif cap.audience == "team":
        w["enterprise_fit"] += 1
    elif cap.audience == "enterprise":
        w["enterprise_fit"] += 2

    # Per-agent access control is the MCP-gradient governance concern.
    if cap.needs_per_agent_access_control:
        w["access_control"] += _ACCESS_CONTROL_WEIGHT

    # Model-in-the-loop favors discovery/judgment; a no-model surface favors
    # the deterministic CLI (scripting / CI, no model needed to invoke).
    if cap.needs_model_to_invoke:
        w["runtime_discoverable"] += 1
        w["encodes_judgment"] += 1
    else:
        w["deterministic_surface"] += 1

    # Unix-pipe composability is a pure CLI strength.
    w["deterministic_surface"] += int(cap.composability_need)
    return w


def score_primitives(cap: Capability) -> List[Tuple[str, float]]:
    """Weighted dot-product of capability weights and per-primitive axis
    scores. Returns [(primitive, score), ...] sorted descending."""
    weights = _weights(cap)
    scored: List[Tuple[str, float]] = []
    for prim in PRIMITIVES:
        feats = PRIMITIVE_FEATURE_SCORES[prim]
        total = float(sum(weights[a] * feats[a] for a in AXES))
        scored.append((prim, total))
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return scored


_RATIONALE = {
    "cli": ("Deterministic command surface, Unix-pipe composable, self-describing "
            "via --help, invokable with no model in the loop. The path of least "
            "resistance for a developer in build mode / CI on their own machine."),
    "mcp": ("Model-callable tool server with schemas, runtime-discoverable, "
            "OAuth + scoped per-agent access control through gateways. The "
            "decisive primitive for enterprise teams and unsupervised background "
            "agents that need least-privilege and audit trails."),
    "skill": ("Encoded judgment: what the agent should do and in what order. "
              "Natural language, no install, works for everyone. The meta-layer "
              "that makes CLIs and MCPs effective -- expose it first regardless."),
}


def recommend_primitive(cap: Capability) -> Dict[str, Any]:
    """Pick a PRIMARY primitive and an `also_expose_as` list. The list captures
    the chapter's 'convergence, not competition' thesis: a deterministic
    capability can ALSO be a CLI even when governed as an MCP endpoint, and a
    team/enterprise capability can ALSO be a governed MCP endpoint even when it
    ships as a CLI. One tool, more than one interface."""
    scored = score_primitives(cap)
    top, _ = scored[0]

    also: List[str] = []
    # A deterministic surface can always ALSO be a composable CLI.
    if cap.invocation == "deterministic_command" and "cli" != top:
        also.append("cli")
    # A team/enterprise or access-controlled capability can ALSO be a governed
    # MCP endpoint (the CLI-to-MCP convergence at the gateway).
    if (cap.needs_per_agent_access_control or cap.audience in ("team", "enterprise")) \
            and "mcp" != top and "mcp" not in also:
        also.append("mcp")

    rec: Dict[str, Any] = {
        "recommended": top,
        "also_expose_as": also,
        "scores": dict(scored),
        "rationale": _RATIONALE[top],
    }
    # Skills-first tip: the judgment layer should be authored first regardless,
    # because it encodes how to use the other two effectively (Ch6 profiling tip).
    if top != "skill":
        rec["skills_first_note"] = (
            "Author the SKILL first regardless: it encodes the judgment for "
            "using this "
            f"{top.upper()} effectively (Ch6 'Skills should come first')."
        )
    return rec


def gradient_position(audience: str) -> Dict[str, Any]:
    """Locate an audience on the personal-to-enterprise gradient and name the
    governance implication. The chapter's self-reported setups: personal is
    CLI-heavy (12 skills, a handful of CLIs, 4 MCP servers); work is MCP-heavy
    (16 skills, almost no CLIs, 10+ MCP servers with OS-level sandboxes). Skills
    stay constant across both -- the shift is structural, not preference."""
    if audience not in ("individual", "team", "enterprise"):
        raise ValueError(f"bad audience: {audience}")
    table = {
        "individual": {
            "position": "personal",
            "tool_mix": "CLI-heavy: a handful of CLIs, few MCP servers, "
                        "skills for tone/judgment.",
            "governance": "OS-level trust on a single machine; broad access is "
                          "acceptable because one developer runs the pipeline.",
            "primitive_bias": "cli",
        },
        "team": {
            "position": "mid-gradient",
            "tool_mix": "Mixed: CLIs give way to MCP servers as more "
                        "stakeholders and shared agents appear.",
            "governance": "Shared agents begin to need scoped access; the "
                          "CLI-to-MCP shift starts here.",
            "primitive_bias": "mcp",
        },
        "enterprise": {
            "position": "enterprise",
            "tool_mix": "MCP-heavy: 10+ MCP servers with OS-level sandboxes, "
                        "almost no CLIs, skills still constant.",
            "governance": "Per-agent access control via allowed_tools "
                          "(least-privilege); unsupervised background agents "
                          "cannot be granted broad CLI access.",
            "primitive_bias": "mcp",
        },
    }
    return table[audience]
