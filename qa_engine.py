"""
Enhanced QA over the generated knowledge graph with Gemini API integration.

Primary method: Gemini API for intelligent question answering
Fallback: Rule-based approach for structured questions

Gemini supports:
- Natural language understanding
- Context-aware answers from original text and knowledge graph
- Complex reasoning beyond simple pattern matching

Rule-based fallback supports:
- WHO:   "Who founded SpaceX?"             -> source where relation=founded and target=SpaceX
- WHERE: "Where is Tesla located?"         -> target where relation=located_in and source=Tesla
- WHAT:  "What did Elon Musk found?"       -> targets where source=Elon Musk (optionally relation=founded)
- REL:   "What is the relation between A and B?" -> relation for edge A->B (or B->A)
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass
from typing import Any

import gemini_config


def _clean(s: str) -> str:
    s = (s or "").strip()
    s = s.strip(string.punctuation + " ")
    return s


def _norm(s: str) -> str:
    return _clean(s).lower()


REL_ALIASES: list[tuple[str, str]] = [
    ("founded", "founded"),
    ("found", "founded"),
    ("founder", "founded"),
    ("located in", "located_in"),
    ("located", "located_in"),
    ("based in", "located_in"),
    ("based", "located_in"),
    ("headquartered in", "located_in"),
    ("headquartered", "located_in"),
    ("directed", "directed"),
    ("direct", "directed"),
    ("acted in", "acted_in"),
    ("acted", "acted_in"),
    ("starred in", "acted_in"),
    ("works at", "works_at"),
    ("work at", "works_at"),
    ("employed at", "works_at"),
    ("capital of", "capital_of"),
    ("capital", "capital_of"),
    ("teach", "teaches"),
    ("teaches", "teaches"),
]


# Relations considered "location" for WHERE questions (strict filter)
LOCATION_RELS = frozenset({"located_in", "based_in", "headquartered_in"})


def _infer_relation(question: str) -> str | None:
    q = _norm(question)
    for pat, rel in REL_ALIASES:
        if pat in q:
            return rel
    return None


def _extract_main_verb_relation(question: str) -> str | None:
    """
    Extract a relation verb from common templates, then normalize via aliases.
    Examples:
    - "What does Anita Sharma teach?" -> teaches
    - "Who founded Infosys?" -> founded
    - "Where is X located?" -> located_in
    """
    q = _norm(question)
    # what does X <verb>
    m = re.search(r"\bwhat\s+does\b.*?\b([a-z_]+)\b", q)
    if m:
        v = m.group(1)
        return _infer_relation(v) or v
    # who <verb>
    m = re.search(r"^\s*who\s+([a-z_]+)\b", q)
    if m:
        v = m.group(1)
        return _infer_relation(v) or v
    # where is/was/are/were <entity> <verb>
    m = re.search(r"\bwhere\s+(?:is|was|are|were)\b.*?\b([a-z_]+)\b", q)
    if m:
        v = m.group(1)
        return _infer_relation(v) or v
    return None


@dataclass
class GraphIndex:
    node_id_to_name: dict[str, str]
    node_id_to_type: dict[str, str]
    name_to_node_ids: dict[str, list[str]]
    edges: list[dict[str, Any]]  # {source, target, relation}

    @staticmethod
    def from_graph(graph: dict[str, Any]) -> "GraphIndex":
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        node_id_to_name: dict[str, str] = {}
        node_id_to_type: dict[str, str] = {}
        name_to_node_ids: dict[str, list[str]] = {}
        for n in nodes:
            nid = str(n.get("id"))
            name = str(n.get("name") or "")
            typ = str(n.get("type") or "Other")
            node_id_to_name[nid] = name
            node_id_to_type[nid] = typ
            k = _norm(name)
            if not k:
                continue
            name_to_node_ids.setdefault(k, []).append(nid)
        return GraphIndex(
            node_id_to_name=node_id_to_name,
            node_id_to_type=node_id_to_type,
            name_to_node_ids=name_to_node_ids,
            edges=list(edges),
        )

    def find_best_node_id_in_text(self, text: str) -> str | None:
        """Longest substring match of node name within the question (case-insensitive)."""
        q = " " + _norm(text) + " "
        best = None
        best_len = 0
        for name_key, ids in self.name_to_node_ids.items():
            if not name_key:
                continue
            if (" " + name_key + " ") in q or name_key in q:
                if len(name_key) > best_len:
                    best = ids[0]
                    best_len = len(name_key)
        return best

    def find_two_nodes_in_text(self, text: str) -> tuple[str | None, str | None]:
        q = " " + _norm(text) + " "
        matches: list[tuple[int, str]] = []
        for name_key, ids in self.name_to_node_ids.items():
            if not name_key:
                continue
            if (" " + name_key + " ") in q or name_key in q:
                matches.append((len(name_key), ids[0]))
        matches.sort(reverse=True)
        if not matches:
            return None, None
        if len(matches) == 1:
            return matches[0][1], None
        return matches[0][1], matches[1][1]

    def outgoing(self, source_id: str, relation: str | None = None) -> list[dict[str, Any]]:
        reln = _norm(relation) if relation else None
        out = []
        for e in self.edges:
            if str(e.get("source")) != str(source_id):
                continue
            if reln and _norm(e.get("relation") or "") != reln:
                continue
            out.append(e)
        return out

    def incoming(self, target_id: str, relation: str | None = None) -> list[dict[str, Any]]:
        reln = _norm(relation) if relation else None
        out = []
        for e in self.edges:
            if str(e.get("target")) != str(target_id):
                continue
            if reln and _norm(e.get("relation") or "") != reln:
                continue
            out.append(e)
        return out

    def relation_between(self, a_id: str, b_id: str) -> str | None:
        for e in self.edges:
            if str(e.get("source")) == str(a_id) and str(e.get("target")) == str(b_id):
                return str(e.get("relation") or "").strip() or None
        for e in self.edges:
            if str(e.get("source")) == str(b_id) and str(e.get("target")) == str(a_id):
                return str(e.get("relation") or "").strip() or None
        return None


def answer_question(user_question: str, graph_data: dict[str, Any], original_text: str = "") -> str:
    """
    Enhanced question answering using Gemini API with fallback to rule-based approach.
    
    Args:
        user_question: The user's question
        graph_data: Knowledge graph with nodes and edges
        original_text: Original input text for context (optional but recommended)
    
    Returns:
        Answer string
    """
    q_raw = (user_question or "").strip()
    if not q_raw:
        return "Please enter a question."

    # Try Gemini API first if available
    if gemini_config.gemini_config.is_available():
        gemini_result = gemini_config.gemini_config.answer_question_with_gemini(
            q_raw, graph_data, original_text
        )
        
        if gemini_result.get("answer"):
            return gemini_result["answer"]
        
        # If Gemini couldn't answer, fall back to rule-based approach
        if gemini_result.get("method") == "gemini_not_found":
            return _answer_with_rules(q_raw, graph_data)
        
        # If Gemini API failed, also fall back to rules
        if gemini_result.get("method") in ["gemini_failed", "gemini_error"]:
            return _answer_with_rules(q_raw, graph_data)

    # Fallback to rule-based approach
    return _answer_with_rules(q_raw, graph_data)


def _answer_with_rules(user_question: str, graph_data: dict[str, Any]) -> str:
    """
    Original rule-based question answering as fallback.
    """
    q_raw = (user_question or "").strip()
    if not q_raw:
        return "Please enter a question."

    g = GraphIndex.from_graph(graph_data or {})
    if not g.node_id_to_name:
        return "Answer not found in knowledge graph"

    q = _norm(q_raw)
    rel = _infer_relation(q_raw) or _extract_main_verb_relation(q_raw)

    # RELATION questions
    if "relation between" in q or q.startswith("what is the relation") or q.startswith("relation"):
        a_id, b_id = g.find_two_nodes_in_text(q_raw)
        if not a_id or not b_id:
            return "Answer not found in knowledge graph"
        r = g.relation_between(a_id, b_id)
        if not r:
            return "Answer not found in knowledge graph"
        a = g.node_id_to_name.get(a_id, "Entity A")
        b = g.node_id_to_name.get(b_id, "Entity B")
        return f"The relation between {a} and {b} is {r}"

    # WHO questions: target entity; return source(s)
    if q.startswith("who"):
        target_id = g.find_best_node_id_in_text(q_raw)
        if not target_id:
            return "Answer not found in knowledge graph"
        use_rel = rel or "founded"
        inc = g.incoming(target_id, use_rel)
        if not inc:
            return "Answer not found in knowledge graph"
        sources = [g.node_id_to_name.get(str(e.get("source")), "") for e in inc]
        sources = [s for s in sources if s]
        if not sources:
            return "Answer not found in knowledge graph"
        tgt = g.node_id_to_name.get(target_id, "")
        if not tgt:
            return "Answer not found in knowledge graph"
        src = sources[0]
        rtxt = (use_rel or "").strip()
        return f"{src} {rtxt} {tgt}"

    # WHERE questions: source entity; return target(s) for located_in
    if q.startswith("where"):
        source_id = g.find_best_node_id_in_text(q_raw)
        if not source_id:
            return "Answer not found in knowledge graph"
        # Strict: only allow location relations
        use_rel = rel if (rel and _norm(rel) in LOCATION_RELS) else "located_in"
        outs = g.outgoing(source_id, use_rel)
        if not outs and use_rel != "located_in":
            outs = g.outgoing(source_id, "located_in")
        if not outs:
            outs = g.outgoing(source_id, "based_in")
        if not outs:
            outs = g.outgoing(source_id, "headquartered_in")
        if not outs:
            return "Answer not found in knowledge graph"
        targets = [g.node_id_to_name.get(str(e.get("target")), "") for e in outs]
        targets = [t for t in targets if t]
        src = g.node_id_to_name.get(source_id, "")
        if not src or not targets:
            return "Answer not found in knowledge graph"
        rel_out = str(outs[0].get("relation") or use_rel).strip()
        phrase = "located in" if _norm(rel_out) in LOCATION_RELS else rel_out
        return f"{src} is {phrase} {targets[0]}"

    # WHAT questions: source entity; return targets (optionally filtered by relation)
    if q.startswith("what"):
        source_id = g.find_best_node_id_in_text(q_raw)
        if not source_id:
            return "Answer not found in knowledge graph"
        # Strict: require relation for WHAT questions (e.g., teaches/founded)
        if not rel:
            return "Answer not found in knowledge graph"
        outs = g.outgoing(source_id, rel)
        if not outs:
            return "Answer not found in knowledge graph"
        targets = [g.node_id_to_name.get(str(e.get("target")), "") for e in outs]
        targets = [t for t in targets if t]
        src = g.node_id_to_name.get(source_id, "")
        if not targets:
            return "Answer not found in knowledge graph"
        if not src:
            return "Answer not found in knowledge graph"
        return f"{src} {rel} {targets[0]}"

    # Default: try relation lookup for two entities, else outgoing for best entity
    a_id, b_id = g.find_two_nodes_in_text(q_raw)
    if a_id and b_id:
        r = g.relation_between(a_id, b_id)
        if r:
            a = g.node_id_to_name.get(a_id, "Entity A")
            b = g.node_id_to_name.get(b_id, "Entity B")
            return f"{a} {r} {b}"

    if a_id:
        outs = g.outgoing(a_id, rel) if rel else g.outgoing(a_id, None)
        if outs:
            e = outs[0]
            a = g.node_id_to_name.get(str(e.get("source")), "")
            b = g.node_id_to_name.get(str(e.get("target")), "")
            r = str(e.get("relation") or "").strip()
            if a and b and r:
                return f"{a} {r} {b}"

    return "Answer not found in knowledge graph"

