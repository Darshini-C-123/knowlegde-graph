"""
Agent 3: Deduplicator — normalize, merge synonyms, dedupe edges.
"""
from __future__ import annotations

import re
from typing import Any

# Known synonym merges (normalized key -> canonical display form)
SYNONYMS: dict[str, str] = {
    "usa": "United States",
    "u.s.a": "United States",
    "u.s.": "United States",
    "us": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
}


def normalize_key(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def apply_synonym(name: str) -> str:
    k = normalize_key(name)
    if k in SYNONYMS:
        return SYNONYMS[k]
    return name.strip()


def dedupe_entities(entities: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Merge by normalized key; prefer longer / synonym-resolved label."""
    by_key: dict[str, dict] = {}
    removed = 0
    for e in entities:
        text = apply_synonym(e.get("text", ""))
        key = normalize_key(text)
        if not key:
            removed += 1
            continue
        if key not in by_key:
            by_key[key] = {**e, "text": text}
        else:
            removed += 1
            existing = by_key[key]["text"]
            if len(text) > len(existing):
                by_key[key]["text"] = text
    return list(by_key.values()), removed


def dedupe_relations(
    relations: list[dict[str, Any]],
    entity_key_to_display: dict[str, str],
) -> tuple[list[dict[str, Any]], int]:
    seen: set[tuple[str, str, str]] = set()
    out = []
    removed = 0
    for r in relations:
        s = entity_key_to_display.get(normalize_key(r.get("source", "")), r.get("source", "").strip())
        t = entity_key_to_display.get(normalize_key(r.get("target", "")), r.get("target", "").strip())
        rel = (r.get("relation") or "").strip().lower()
        sk, tk = normalize_key(s), normalize_key(t)
        key = (sk, tk, rel)
        if sk == tk:
            removed += 1
            continue
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        out.append({**r, "source": s, "target": t, "relation": r.get("relation", "")})
    return out, removed


def run(
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    use_similarity: bool = False,
) -> dict[str, Any]:
    _ = use_similarity  # reserved for optional fuzzy dedupe
    ents, dup_ent = dedupe_entities(entities)

    key_to_display = {normalize_key(e["text"]): e["text"] for e in ents}
    rels, dup_rel = dedupe_relations(relations, key_to_display)

    return {
        "entities": ents,
        "relations": rels,
        "duplicates_removed": dup_ent + dup_rel,
        "entity_duplicates_removed": dup_ent,
        "relation_duplicates_removed": dup_rel,
    }
