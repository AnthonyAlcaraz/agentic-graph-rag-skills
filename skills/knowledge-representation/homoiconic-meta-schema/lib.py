"""
Homoiconic Knowledge Representation (Ch3 "Homoiconic Knowledge Representation").

Homoiconicity = code and data share the same representation, so agents can
inspect and modify their own knowledge structures with the same mechanisms they
use for regular data. Two constructs from the chapter:

  1. Meta-knowledge structures (Example 3-6): a metaschema describes what an
     EntityType is; entity-type definitions are then stored AS DATA using the
     same representation. This module validates that an entity-type definition
     conforms to the metaschema, and that a data instance conforms to its
     entity-type definition -- the same validator works at both levels (that is
     the homoiconic property made operational).

  2. Executable knowledge patterns (Example 3-7): operational rules stored as
     graph entities with `condition` + `action` components. This module parses
     and validates such a Rule and evaluates its tiered action against a fact
     (the DetermineCustomerSegment example: >20 -> Premium, >10 -> Regular,
     else Basic).

Pure Python, stdlib only. No graph database; the metaschema IS the data.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# The metaschema: it describes the schema itself (Example 3-6). An EntityType
# has a name (required), an optional description, and a list of property
# definitions.
METASCHEMA: Dict[str, Any] = {
    "type": "EntityType",
    "properties": [
        {"name": "name", "type": "string", "required": True},
        {"name": "description", "type": "string", "required": False},
        {"name": "properties", "type": "list", "items": "PropertyDefinition",
         "required": True},
    ],
}

# A PropertyDefinition (the items of EntityType.properties) has a name + type,
# optional 'required'.
VALID_PROPERTY_TYPES = {"string", "date", "int", "float", "bool", "list"}


def validate_entity_type(definition: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an entity-type definition against the metaschema.

    A valid definition (the Person example from Example 3-6):
      {"name": "Person", "description": "...",
       "properties": [{"name": "name", "type": "string", "required": true}, ...]}

    Returns {valid, errors}.
    """
    errors: List[str] = []
    # name required, must be a non-empty string.
    name = definition.get("name")
    if not isinstance(name, str) or not name:
        errors.append("entity type missing required non-empty 'name'")
    # properties required, must be a list of PropertyDefinition.
    props = definition.get("properties")
    if not isinstance(props, list):
        errors.append("entity type 'properties' must be a list")
        props = []
    seen = set()
    for i, p in enumerate(props):
        if not isinstance(p, dict):
            errors.append(f"property[{i}] is not an object")
            continue
        pname = p.get("name")
        if not isinstance(pname, str) or not pname:
            errors.append(f"property[{i}] missing 'name'")
        elif pname in seen:
            errors.append(f"property name '{pname}' duplicated (names must be unique)")
        else:
            seen.add(pname)
        ptype = p.get("type")
        if ptype not in VALID_PROPERTY_TYPES:
            errors.append(f"property '{pname}' has invalid type '{ptype}' "
                          f"(expected one of {sorted(VALID_PROPERTY_TYPES)})")
    return {"valid": not errors, "errors": errors}


def validate_data_against_type(
    entity_type: Dict[str, Any], instance: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate a data instance against its entity-type definition.

    This is the SAME shape of validation as validate_entity_type, applied one
    level down -- the homoiconic property: schema and data share representation,
    so the same machinery checks both.

    Returns {valid, errors}.
    """
    errors: List[str] = []
    props = {p["name"]: p for p in entity_type.get("properties", [])
             if isinstance(p, dict) and "name" in p}
    # required properties present?
    for pname, pdef in props.items():
        if pdef.get("required") and pname not in instance:
            errors.append(f"instance missing required property '{pname}'")
    # types match? (light check; the seam for a real type system)
    _checkers = {
        "string": lambda v: isinstance(v, str),
        "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "bool": lambda v: isinstance(v, bool),
        "list": lambda v: isinstance(v, list),
        "date": lambda v: isinstance(v, str),  # TODO: real date parse at seam
    }
    for key, val in instance.items():
        if key in props:
            ptype = props[key].get("type")
            checker = _checkers.get(ptype)
            if checker and not checker(val):
                errors.append(f"property '{key}' value {val!r} does not match type '{ptype}'")
    return {"valid": not errors, "errors": errors}


# ---------------------------------------------------------------------------
# Executable knowledge patterns (Example 3-7). A Rule is an entity with a
# condition (graph pattern match) and an action (tiered WHEN/THEN logic).
# ---------------------------------------------------------------------------

_WHEN_RE = re.compile(
    r"WHEN\s+(\w+)\s*([<>]=?)\s*([\d.]+)\s+THEN\s+SET\s+\w+\.(\w+)\s*=\s*'([^']+)'",
    re.IGNORECASE,
)
_ELSE_RE = re.compile(r"ELSE\s+SET\s+\w+\.(\w+)\s*=\s*'([^']+)'", re.IGNORECASE)


def validate_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an executable-knowledge Rule entity (Example 3-7).

    Required keys: name, condition, action. Action must contain at least one
    parseable WHEN...THEN clause. Returns {valid, errors, parsed_clauses}.
    """
    errors: List[str] = []
    for key in ("name", "condition", "action"):
        if not rule.get(key):
            errors.append(f"rule missing required '{key}'")
    action = rule.get("action", "")
    clauses = parse_action(action) if action else {"when": [], "else": None}
    if not clauses["when"]:
        errors.append("rule action has no parseable WHEN...THEN clause")
    return {"valid": not errors, "errors": errors, "parsed_clauses": clauses}


def parse_action(action_text: str) -> Dict[str, Any]:
    """Parse the tiered WHEN/THEN/ELSE action body into structured clauses.

    Returns {"when": [{var, op, threshold, field, value}, ...], "else": {...}}.
    The clauses are kept in source order (tiered evaluation depends on order).
    """
    when_clauses = []
    for m in _WHEN_RE.finditer(action_text):
        var, op, threshold, field, value = m.groups()
        when_clauses.append({
            "var": var, "op": op, "threshold": float(threshold),
            "field": field, "value": value,
        })
    else_clause = None
    em = _ELSE_RE.search(action_text)
    if em:
        else_clause = {"field": em.group(1), "value": em.group(2)}
    return {"when": when_clauses, "else": else_clause}


def evaluate_rule(rule: Dict[str, Any], facts: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Evaluate a Rule's tiered action against a fact dict.

    facts: {var_name: numeric_value}. Returns {field: value} for the first
    matching WHEN clause (source order), or the ELSE assignment, or None.

    Worked example (DetermineCustomerSegment): purchase_count 25 -> Premium,
    15 -> Regular, 3 -> Basic.
    """
    clauses = parse_action(rule.get("action", ""))
    for c in clauses["when"]:
        v = facts.get(c["var"])
        if v is None:
            continue
        if _cmp(v, c["op"], c["threshold"]):
            return {c["field"]: c["value"]}
    if clauses["else"]:
        return {clauses["else"]["field"]: clauses["else"]["value"]}
    return None


def _cmp(v: float, op: str, threshold: float) -> bool:
    if op == ">":
        return v > threshold
    if op == ">=":
        return v >= threshold
    if op == "<":
        return v < threshold
    if op == "<=":
        return v <= threshold
    raise ValueError(f"unsupported operator '{op}'")
