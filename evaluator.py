"""
Agent 5: Evaluator — graph metrics.
"""
from __future__ import annotations

from typing import Any


def graph_density(num_nodes: int, num_edges: int, directed: bool = True) -> float:
    if num_nodes < 2:
        return 0.0
    max_e = num_nodes * (num_nodes - 1)
    if not directed:
        max_e //= 2
    if max_e <= 0:
        return 0.0
    return num_edges / max_e


def average_degree(num_nodes: int, num_edges: int, directed: bool = True) -> float:
    if num_nodes == 0:
        return 0.0
    if directed:
        return (num_edges * 2) / num_nodes
    return (num_edges * 2) / num_nodes


def evaluate(
    graph: dict[str, Any],
    duplicates_removed: int,
    validation_accuracy: float,
    baseline_duplicates: int | None = None,
) -> dict[str, Any]:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    n = len(nodes)
    m = len(edges)
    dens = graph_density(n, m)
    avg_deg = average_degree(n, m)
    return {
        "node_count": n,
        "edge_count": m,
        "duplicates_removed": duplicates_removed,
        # validation_accuracy is kept for backwards-compat; accuracy focuses on relations.
        "validation_accuracy": round(validation_accuracy, 4),
        "accuracy": round(validation_accuracy, 4),
        "graph_density": round(dens, 6),
        "average_degree": round(avg_deg, 4),
        "baseline_duplicates": baseline_duplicates,
    }
