"""
Knowledge Organization Spectrum classifier + ontology core-component validator
(Ch3 "Knowledge Organization and Ontology Fundamentals").

The chapter places knowledge-organization systems on a spectrum simple->complex:

  pick_list   controlled value list, NO hierarchy (country list, currency codes)
  taxonomy    parent-child hierarchy with predefined terms + synonyms
  thesaurus   taxonomy + generic associated/related relationships
  ontology    graph/network: classes + properties + expanded relationship types
              + scope notes + inference

This module (1) classifies a vocabulary specification onto the spectrum by the
structural features it exhibits, and (2) validates that something claiming to be
an ontology actually carries the five core components the chapter names:
classes, subclasses, individuals, axioms, relationships (object properties).

Pure Python, stdlib only.
"""

from __future__ import annotations

from typing import Any, Dict, List


SPECTRUM = ["pick_list", "taxonomy", "thesaurus", "ontology"]

# The five ontology core components (Ch3 "Ontology core components").
ONTOLOGY_COMPONENTS = ["classes", "subclasses", "individuals", "axioms",
                       "relationships"]


def classify(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a vocabulary spec onto the knowledge-organization spectrum.

    spec is a feature dict; the relevant booleans/collections:
      values:           list of controlled values (any vocabulary has these)
      has_hierarchy:    parent-child relationships present
      has_synonyms:     synonym/alt-label sets present
      has_associative:  generic 'related'/associative links present
      has_classes:      class definitions present
      has_properties:   object-property / relationship-type definitions present
      has_inference:    inference rules / axioms present

    Returns {classification, reasons, spectrum_index}.
    The classification is the MOST complex tier whose defining features are met,
    walked from the bottom up so a partial ontology does not over-claim.
    """
    reasons: List[str] = []
    has_hierarchy = bool(spec.get("has_hierarchy"))
    has_synonyms = bool(spec.get("has_synonyms"))
    has_associative = bool(spec.get("has_associative"))
    has_classes = bool(spec.get("has_classes"))
    has_properties = bool(spec.get("has_properties"))
    has_inference = bool(spec.get("has_inference"))

    # Ontology: classes + properties + (inference OR expanded relationships).
    if has_classes and has_properties and (has_inference or has_associative):
        reasons.append("classes + object properties + inference/expanded "
                       "relationships -> ontology (network of nodes+relationships)")
        return _result("ontology", reasons)

    # Thesaurus: hierarchy + synonyms + associative relationships.
    if has_hierarchy and has_synonyms and has_associative:
        reasons.append("hierarchy + synonyms + associative relationships -> "
                       "thesaurus (taxonomy extended with related-to links)")
        return _result("thesaurus", reasons)

    # Taxonomy: hierarchy with predefined terms (synonyms optional).
    if has_hierarchy:
        reasons.append("parent-child hierarchy present -> taxonomy")
        if has_synonyms:
            reasons.append("synonyms present (still a taxonomy without associative links)")
        return _result("taxonomy", reasons)

    # Pick list: controlled values, no hierarchy.
    reasons.append("controlled value list, no hierarchical structure -> pick_list")
    return _result("pick_list", reasons)


def _result(classification: str, reasons: List[str]) -> Dict[str, Any]:
    return {
        "classification": classification,
        "spectrum_index": SPECTRUM.index(classification),
        "reasons": reasons,
    }


def validate_ontology_components(ontology: Dict[str, Any]) -> Dict[str, Any]:
    """Validate that an ontology carries the five core components.

    ontology shape (each a non-empty collection when present):
      classes:       [class definitions]
      subclasses:    [subclass definitions] (each should reference a parent)
      individuals:   [instance records]
      axioms:        [rules/constraints]
      relationships: [object-property definitions]  (each connects two classes)

    Returns {valid, present, missing, errors}.
    """
    present = []
    missing = []
    errors: List[str] = []
    for comp in ONTOLOGY_COMPONENTS:
        val = ontology.get(comp)
        if val:
            present.append(comp)
        else:
            missing.append(comp)

    # Structural checks the chapter's AI-assisted validation names:
    # subclasses should reference an existing class (parent inheritance),
    # relationships should reference existing classes (no dangling endpoints).
    class_names = {c.get("name") for c in ontology.get("classes", []) if isinstance(c, dict)}
    for sc in ontology.get("subclasses", []):
        if isinstance(sc, dict):
            parent = sc.get("parent")
            if parent and class_names and parent not in class_names:
                errors.append(f"subclass '{sc.get('name')}' references unknown parent "
                              f"class '{parent}'")
    for rel in ontology.get("relationships", []):
        if isinstance(rel, dict):
            for endpoint in ("from", "to"):
                ref = rel.get(endpoint)
                if ref and class_names and ref not in class_names:
                    errors.append(f"relationship '{rel.get('name')}' {endpoint} "
                                  f"references unknown class '{ref}'")

    valid = not missing and not errors
    return {"valid": valid, "present": present, "missing": missing, "errors": errors}


def recommend_upgrade(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Given a current classification, name what to add to reach the next tier.

    The chapter's argument for ontologies: flexibility -- pick lists/taxonomies/
    thesauruses require reorganizing whole hierarchies to add instances, while
    ontologies expand without structural disruption.
    """
    current = classify(spec)["classification"]
    nxt = {
        "pick_list": ("taxonomy", "add parent-child hierarchy with predefined terms"),
        "taxonomy": ("thesaurus", "add synonyms and generic associative ('related') relationships"),
        "thesaurus": ("ontology", "add class definitions, object properties, and inference/axioms"),
        "ontology": (None, "already the most flexible tier; expands without structural disruption"),
    }
    target, action = nxt[current]
    return {"current": current, "next": target, "action": action}
