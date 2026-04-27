"""
Orchestrates multi-agent state machine and baseline (extraction-only) path.
States: INIT → EXTRACTING → VALIDATING → DEDUPLICATING → CURATING → EVALUATING → COMPLETED

Features:
 - Run IDs (UUID) assigned to every execution
 - Structured JSON message envelopes per agent
 - Timestamped logs with detailed I/O
 - State transition history
 - Run storage for replay
 - Graph growth tracking across runs
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

import curator
import deduplicator
import evaluator
import extractor
import validator


LogFn = Callable[[str], None]

# ── In-memory run store (replay + growth tracking) ──────────────────────────
_run_history: list[dict[str, Any]] = []
_MAX_STORED_RUNS = 50


def get_run_history() -> list[dict[str, Any]]:
    """Return list of stored runs (most-recent first)."""
    return list(reversed(_run_history))


def get_run_by_id(run_id: str) -> dict[str, Any] | None:
    for r in _run_history:
        if r.get("run_id") == run_id:
            return r
    return None


def get_graph_growth() -> list[dict[str, Any]]:
    """Return [{run_id, timestamp, node_count, edge_count, cumulative_nodes, cumulative_edges}]."""
    result = []
    cum_nodes = 0
    cum_edges = 0
    for r in _run_history:
        m = r.get("with_agents", {}).get("metrics", {})
        n = m.get("node_count", 0)
        e = m.get("edge_count", 0)
        cum_nodes += n
        cum_edges += e
        result.append({
            "run_id": r["run_id"],
            "timestamp": r["timestamp"],
            "node_count": n,
            "edge_count": e,
            "cumulative_nodes": cum_nodes,
            "cumulative_edges": cum_edges,
        })
    return result


# ── Helpers ─────────────────────────────────────────────────────────────────

def _ts() -> str:
    """ISO-8601 timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _msg(
    agent: str,
    action: str,
    run_id: str,
    input_summary: str,
    output_summary: str,
    state_from: str | None = None,
    state_to: str | None = None,
) -> dict[str, Any]:
    """Structured JSON message envelope."""
    m: dict[str, Any] = {
        "agent": agent,
        "action": action,
        "run_id": run_id,
        "timestamp": _ts(),
        "input_summary": input_summary,
        "output_summary": output_summary,
    }
    if state_from:
        m["state_from"] = state_from
    if state_to:
        m["state_to"] = state_to
    return m


def _ensure_entities_from_relations(
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add missing endpoints as Other so graph can include all edges."""
    texts = {e["text"].lower() for e in entities}
    out = list(entities)
    for r in relations:
        for key in ("source", "target"):
            t = (r.get(key) or "").strip()
            if not t:
                continue
            tl = t.lower()
            if tl not in texts:
                texts.add(tl)
                out.append({"text": t, "label": "MISC", "type": "Other"})
    return out


def _count_raw_duplicates(entities: list[dict[str, Any]], relations: list[dict[str, Any]]) -> int:
    keys = [e["text"].strip().lower() for e in entities]
    keys += [
        (r.get("source") or "").lower()
        + "|"
        + (r.get("target") or "").lower()
        + "|"
        + (r.get("relation") or "").lower()
        for r in relations
    ]
    c = Counter(keys)
    return sum(max(0, v - 1) for v in c.values())




# ── Full pipeline with structured messages ──────────────────────────────────

def run(
    text: str,
    log: LogFn | None = None,
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())[:8]
    logs: list[str] = []
    messages: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    agent_timeline: list[dict[str, Any]] = []

    def _log(msg: str) -> None:
        logs.append(msg)
        if log:
            log(msg)

    def _transition(from_state: str, to_state: str) -> None:
        t = {"from": from_state, "to": to_state, "timestamp": _ts()}
        transitions.append(t)
        _log(f"[{_ts()}] [STATE] {from_state} → {to_state}")

    def _agent_start(name: str) -> dict[str, Any]:
        entry = {"agent": name, "status": "running", "start": _ts(), "end": None}
        agent_timeline.append(entry)
        return entry

    def _agent_end(entry: dict[str, Any]) -> None:
        entry["status"] = "done"
        entry["end"] = _ts()

    # ── INIT ──
    _log(f"[{_ts()}] [RUN {run_id}] Pipeline started")
    _transition("INIT", "EXTRACTING")

    # ── EXTRACTING ──
    ae = _agent_start("Extractor")
    ex = extractor.extract(text)
    _agent_end(ae)
    m = _msg("Extractor", "extract", run_id,
             f"text ({len(text)} chars)",
             f"{len(ex['entities'])} entities, {len(ex['relations'])} relations")
    messages.append(m)
    _log(f"[{m['timestamp']}] [EXTRACTOR] in={m['input_summary']}  out={m['output_summary']}")

    _transition("EXTRACTING", "VALIDATING")

    # ── VALIDATING ──
    av = _agent_start("Validator")
    merged_for_val = _ensure_entities_from_relations(ex["entities"], ex["relations"])
    val = validator.validate(merged_for_val, ex["relations"])
    _agent_end(av)
    rel_acc = val.get("relation_accuracy", val["validation_accuracy"])
    m = _msg("Validator", "validate", run_id,
             f"{len(merged_for_val)} entities, {len(ex['relations'])} relations",
             f"kept {len(val['entities'])} entities, {len(val['relations'])} rels, accuracy={rel_acc:.3f}",
             "EXTRACTING", "VALIDATING")
    messages.append(m)
    _log(f"[{m['timestamp']}] [VALIDATOR] in={m['input_summary']}  out={m['output_summary']}")

    _transition("VALIDATING", "DEDUPLICATING")

    # ── DEDUPLICATING ──
    ad = _agent_start("Deduplicator")
    ded = deduplicator.run(val["entities"], val["relations"], use_similarity=False)
    _agent_end(ad)
    m = _msg("Deduplicator", "deduplicate", run_id,
             f"{len(val['entities'])} entities, {len(val['relations'])} relations",
             f"removed {ded['duplicates_removed']} duplicates")
    messages.append(m)
    _log(f"[{m['timestamp']}] [DEDUPLICATOR] in={m['input_summary']}  out={m['output_summary']}")

    _transition("DEDUPLICATING", "CURATING")

    # ── CURATING ──
    ac = _agent_start("Curator")
    cur = curator.run(ded["entities"], ded["relations"])
    graph = cur["graph"]
    _agent_end(ac)
    m = _msg("Curator", "curate", run_id,
             f"{len(ded['entities'])} entities, {len(ded['relations'])} relations",
             f"nodes={len(graph['nodes'])} edges={len(graph['edges'])}")
    messages.append(m)
    _log(f"[{m['timestamp']}] [CURATOR] in={m['input_summary']}  out={m['output_summary']}")

    _transition("CURATING", "EVALUATING")

    # ── EVALUATING ──
    aev = _agent_start("Evaluator")
    ev = evaluator.evaluate(
        graph,
        duplicates_removed=ded["duplicates_removed"],
        validation_accuracy=rel_acc,
    )
    _agent_end(aev)
    m = _msg("Evaluator", "evaluate", run_id,
             f"graph with {len(graph['nodes'])} nodes, {len(graph['edges'])} edges",
             f"density={ev['graph_density']} degree={ev['average_degree']}")
    messages.append(m)
    _log(f"[{m['timestamp']}] [EVALUATOR] in={m['input_summary']}  out={m['output_summary']}")

    _transition("EVALUATING", "COMPLETED")
    _log(f"[{_ts()}] [COMPLETED] OK (run {run_id})")

    result = {
        "run_id": run_id,
        "timestamp": _ts(),
        "graph": graph,
        "metrics": ev,
        "validation_accuracy": rel_acc,
        "logs": logs,
        "messages": messages,
        "transitions": transitions,
        "agent_timeline": agent_timeline,
        "original_text": text,  # Store original text for Gemini QA context
    }

    # ── Store for replay / graph-growth ──
    _run_history.append(result)
    if len(_run_history) > _MAX_STORED_RUNS:
        _run_history.pop(0)

    return result




