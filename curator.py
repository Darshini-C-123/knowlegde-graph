"""
Agent 4: Curator — structured graph JSON and relation standardization.
"""
from __future__ import annotations

import json
from typing import Any

RELATION_STANDARD: dict[str, str] = {
    "act": "acted_in",
    "acted": "acted_in",
    "star": "acted_in",
    "direct": "directed",
    "directed": "directed",
    "work": "works_at",
    "works": "works_at",
    "employ": "works_at",
    "locate": "located_in",
    "located": "located_in",
    "found": "founded",
    "founder": "founded",
    "capital_of": "capital_of",
    "be": "is_a",
    "is": "is_a",
}


def standardize_relation(lemma: str) -> str:
    base = (lemma or "").strip().lower()
    return RELATION_STANDARD.get(base, base)


def build_graph(entities: list[dict[str, Any]], relations: list[dict[str, Any]]) -> dict[str, Any]:
    """Assign stable string ids; produce nodes and edges."""
    nodes: list[dict[str, Any]] = []
    name_to_id: dict[str, str] = {}
    for i, e in enumerate(entities):
        nid = str(i + 1)
        name_to_id[e["text"].lower()] = nid
        nodes.append(
            {
                "id": nid,
                "name": e["text"],
                "type": e.get("type", "Other"),
            }
        )

    edges: list[dict[str, Any]] = []
    for r in relations:
        s = (r.get("source") or "").strip()
        t = (r.get("target") or "").strip()
        sk, tk = s.lower(), t.lower()
        if sk not in name_to_id or tk not in name_to_id:
            continue
        rel = standardize_relation(r.get("relation", ""))
        edges.append(
            {
                "source": name_to_id[sk],
                "target": name_to_id[tk],
                "relation": rel,
            }
        )

    return {"nodes": nodes, "edges": edges}


def to_json_serializable(graph: dict[str, Any]) -> str:
    return json.dumps(graph, ensure_ascii=False, indent=2)


def run(entities: list[dict[str, Any]], relations: list[dict[str, Any]]) -> dict[str, Any]:
    graph = build_graph(entities, relations)
    return {"graph": graph}
