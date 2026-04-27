"""
Agent 2: Validator — filter invalid entities and relationships.
Keeps lowercase / informal mentions when they are substantive (real-world text).
"""
from __future__ import annotations

from typing import Any

_STOPWORDS = frozenset(
    """
    a an the and or but if in on at to for of as by with from up about into over after
    be is are was were been being have has had do does did will would could should may might must
    this that these those it its they them their we you he she i my your his her
    not no yes so than then there here when where what which who whom how why
    all each every both few more most other some such only same own than too very
    can just also now um uh ok
    """.split()
)


def _entity_text_ok(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 2:
        return False
    low = t.lower()
    if low in _STOPWORDS:
        return False
    if t[0].isupper() or t.isupper():
        return True
    if len(low) >= 3:
        return True
    # Two-letter acronyms (e.g., AI, UK)
    if len(t) == 2 and t.isalpha() and t.isupper():
        return True
    if any(ch.isdigit() for ch in t):
        return True
    return len(t) >= 2 and not low.isalpha()  # e.g. "c++"


def validate_entities(entities: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kept = []
    rejected = 0
    for e in entities:
        text = (e.get("text") or "").strip()
        if not _entity_text_ok(text):
            rejected += 1
            continue
        kept.append(e)

    n = len(entities)
    entity_acc = (len(kept) / n) if n else 1.0
    return kept, {"rejected_entities": rejected, "entity_accuracy": entity_acc, "total_entities": n}


def validate_relations(
    relations: list[dict[str, Any]],
    entity_texts: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    norm_set = {t.lower() for t in entity_texts}
    kept = []
    rejected = 0
    for r in relations:
        s = (r.get("source") or "").strip()
        t = (r.get("target") or "").strip()
        if not s or not t:
            rejected += 1
            continue
        if s.lower() not in norm_set or t.lower() not in norm_set:
            rejected += 1
            continue
        kept.append(r)

    n = len(relations)
    rel_acc = (len(kept) / n) if n else 1.0
    return kept, {"rejected_relations": rejected, "relation_accuracy": rel_acc, "total_relations": n}


def validate(
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> dict[str, Any]:
    ent_kept, ent_stats = validate_entities(entities)
    texts = {e["text"] for e in ent_kept}
    rel_kept, rel_stats = validate_relations(relations, texts)

    te = ent_stats["total_entities"]
    tr = rel_stats["total_relations"]
    if te + tr == 0:
        validation_accuracy = 1.0
    else:
        validation_accuracy = (len(ent_kept) + len(rel_kept)) / (te + tr)

    relation_accuracy = rel_stats.get("relation_accuracy", 1.0)

    return {
        "entities": ent_kept,
        "relations": rel_kept,
        "validation_accuracy": validation_accuracy,
        # For metrics focused on relationships:
        "relation_accuracy": relation_accuracy,
        "stats": {
            **ent_stats,
            **rel_stats,
        },
    }
