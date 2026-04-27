"""
Agent 1: Extractor — spaCy + OpenIE-style dependency extraction + fallbacks
so varied input (informal text, no NER, odd parses) still yields a graph.
Enhanced with Gemini API for improved entity and relation extraction.
"""
from __future__ import annotations

import re
import string
from typing import Any

import spacy

import gemini_config

_nlp = None


def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


ENTITY_MAP = {
    "PERSON": "Person",
    "ORG": "Organization",
    "GPE": "Location",
    "LOC": "Location",
    "WORK_OF_ART": "Event",
    "FAC": "Location",
    "NORP": "Organization",
    "PRODUCT": "Other",
    "EVENT": "Event",
    "LANGUAGE": "Other",
    "LAW": "Other",
}


def clean_span_text(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r"^[" + re.escape(string.punctuation) + r"]+", "", t)
    t = re.sub(r"[" + re.escape(string.punctuation) + r"]+$", "", t)
    return t.strip()


def map_entity_label(spacy_label: str) -> str:
    return ENTITY_MAP.get(spacy_label, "Other")


def _noun_chunk_span(doc, token) -> str | None:
    if token is None:
        return None
    try:
        for nc in doc.noun_chunks:
            if nc.start <= token.i < nc.end:
                return clean_span_text(nc.text)
    except (ValueError, AttributeError):
        pass
    return None


def _expand_to_span(token) -> str:
    if token is None:
        return ""
    nc = _noun_chunk_span(token.doc, token)
    if nc:
        return nc
    ent = token.doc[token.i]
    if ent.ent_type_:
        start, end = ent.i, ent.i + 1
        while start > 0 and ent.doc[start - 1].ent_type_ == ent.ent_type_:
            start -= 1
        while end < len(ent.doc) and ent.doc[end].ent_type_ == ent.doc[start].ent_type_:
            end += 1
        return clean_span_text(ent.doc[start:end].text)
    return clean_span_text(token.text)


def _find_subject_for_verb(verb) -> Any | None:
    for child in verb.children:
        if child.dep_ in ("nsubj", "nsubj:pass"):
            return child
    return None


def _find_passive_subject(verb) -> Any | None:
    for child in verb.children:
        if child.dep_ in ("nsubjpass", "nsubj:pass"):
            return child
    return None


def _agent_from_by_prep(verb) -> Any | None:
    for child in verb.children:
        if child.dep_ == "prep" and child.text.lower() == "by":
            for pchild in child.children:
                if pchild.dep_ in ("pobj", "dobj", "compound", "flat"):
                    return pchild
            return None
    for child in verb.children:
        if child.dep_ == "agent":
            ch = list(child.children)
            return ch[0] if ch else None
    return None


def _object_candidates(verb) -> list[Any]:
    objs = []
    for child in verb.children:
        if child.dep_ in ("dobj", "attr", "acomp", "xcomp"):
            objs.append(child)
    for child in verb.children:
        if child.dep_ == "prep" and child.text.lower() not in ("by",):
            for pchild in child.children:
                if pchild.dep_ == "pobj":
                    objs.append(pchild)
    return objs


def _relation_key(s: str, t: str, r: str) -> tuple[str, str, str]:
    return (s.strip().lower(), t.strip().lower(), (r or "").strip().lower())


_PRONOUN_ENDPOINTS = frozenset(
    "i me you he him she her we us they them it this that these those who whom".split()
)


def _is_weak_endpoint(span: str) -> bool:
    s = (span or "").strip().lower()
    if len(s) < 2:
        return True
    if s in _PRONOUN_ENDPOINTS:
        return True
    return False


def _drop_low_value_relations(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in relations:
        a, b = (r.get("source") or "").strip(), (r.get("target") or "").strip()
        if _is_weak_endpoint(a) or _is_weak_endpoint(b):
            continue
        out.append(r)
    return out


def _extract_from_verb_head(verb, relations: list[dict], seen: set[tuple]) -> None:
    if verb.pos_ not in ("VERB", "AUX"):
        return

    lemma = verb.lemma_.lower() if verb.lemma_ else verb.text.lower()
    if not lemma or lemma == "-PRON-":
        lemma = verb.text.lower()

    def resolve_arg(tok) -> str:
        if tok is None:
            return ""
        return _expand_to_span(tok)

    subj = _find_subject_for_verb(verb)
    pasv_subj = _find_passive_subject(verb)
    agent = _agent_from_by_prep(verb)

    if pasv_subj is not None and agent is not None:
        movie_span = resolve_arg(pasv_subj)
        director_span = resolve_arg(agent)
        if director_span and movie_span:
            k = _relation_key(director_span, movie_span, lemma)
            if k not in seen:
                seen.add(k)
                relations.append(
                    {
                        "source": director_span,
                        "target": movie_span,
                        "relation": lemma,
                        "passive": True,
                    }
                )
        return

    if lemma == "be" and subj is not None:
        subj_span = resolve_arg(subj)
        for child in verb.children:
            if child.dep_ != "attr":
                continue
            got_capital = False
            for prep in child.children:
                if prep.dep_ == "prep" and prep.text.lower() == "of":
                    for pchild in prep.children:
                        if pchild.dep_ == "pobj":
                            obj_span = resolve_arg(pchild)
                            if subj_span and obj_span:
                                k = _relation_key(subj_span, obj_span, "capital_of")
                                if k not in seen:
                                    seen.add(k)
                                    relations.append(
                                        {
                                            "source": subj_span,
                                            "target": obj_span,
                                            "relation": "capital_of",
                                            "passive": False,
                                        }
                                    )
                                got_capital = True
            if not got_capital:
                attr_span = resolve_arg(child)
                if subj_span and attr_span and subj_span.lower() != attr_span.lower():
                    k = _relation_key(subj_span, attr_span, "is_a")
                    if k not in seen:
                        seen.add(k)
                        relations.append(
                            {
                                "source": subj_span,
                                "target": attr_span,
                                "relation": "is_a",
                                "passive": False,
                            }
                        )
        return

    if subj is not None:
        subj_span = resolve_arg(subj)
        objs = _object_candidates(verb)
        if not objs:
            for child in verb.children:
                if child.dep_ == "prep" and child.text.lower() == "to":
                    for pchild in child.children:
                        if pchild.dep_ == "pobj":
                            objs.append(pchild)
        for obj_tok in objs:
            obj_span = resolve_arg(obj_tok)
            if subj_span and obj_span and subj_span.lower() != obj_span.lower():
                k = _relation_key(subj_span, obj_span, lemma)
                if k not in seen:
                    seen.add(k)
                    relations.append(
                        {
                            "source": subj_span,
                            "target": obj_span,
                            "relation": lemma,
                            "passive": False,
                        }
                    )


def _extract_nominal_root(sent, relations: list[dict], seen: set[tuple]) -> None:
    root = [t for t in sent if t.dep_ == "ROOT"]
    if not root:
        return
    root = root[0]
    if root.pos_ not in ("NOUN", "PROPN", "PRON"):
        return
    head_span = _expand_to_span(root)
    if not head_span or len(head_span) < 2:
        return
    for child in root.children:
        if child.dep_ == "prep" and child.text.lower() in ("of", "in", "for", "at", "from", "to", "with"):
            for pobj in child.children:
                if pobj.dep_ == "pobj":
                    tspan = _expand_to_span(pobj)
                    if tspan and head_span.lower() != tspan.lower():
                        rel = f"nmod_{child.text.lower()}"
                        k = _relation_key(head_span, tspan, rel)
                        if k not in seen:
                            seen.add(k)
                            relations.append(
                                {
                                    "source": head_span,
                                    "target": tspan,
                                    "relation": rel,
                                    "passive": False,
                                }
                            )


def extract_relations_from_sentence(sent, doc) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    for token in sent:
        if token.pos_ in ("VERB", "AUX"):
            if _find_subject_for_verb(token) or _find_passive_subject(token):
                _extract_from_verb_head(token, relations, seen)

    _extract_nominal_root(sent, relations, seen)

    return relations


def _entities_from_ner(doc) -> tuple[list[dict[str, Any]], set[str]]:
    out = []
    keys: set[str] = set()
    for ent in doc.ents:
        name = clean_span_text(ent.text)
        if not name or len(name) < 1:
            continue
        k = name.lower()
        if k in keys:
            continue
        keys.add(k)
        out.append({"text": name, "label": ent.label_, "type": map_entity_label(ent.label_)})
    return out, keys


_JUNK_NOUN_LEMMAS = frozenset(
    """
    capital way thing idea lot point time day part kind sort bit while
    fact reason case moment week year month place name title issue matter
    """.split()
)


def _entities_from_noun_chunks(doc, existing_keys: set[str]) -> list[dict[str, Any]]:
    added = []
    try:
        chunks = list(doc.noun_chunks)
    except ValueError:
        chunks = []
    for nc in chunks:
        text = clean_span_text(nc.text)
        if len(text) < 2:
            continue
        k = text.lower()
        if k in existing_keys:
            continue
        root = nc.root
        if root.pos_ == "PRON":
            continue
        has_propn = any(t.pos_ == "PROPN" for t in nc)
        if root.lemma_.lower() in _JUNK_NOUN_LEMMAS and not has_propn:
            continue
        if has_propn or (root.pos_ in ("NOUN", "PROPN") and len(text) >= 3):
            existing_keys.add(k)
            added.append({"text": text, "label": "NOUN_CHUNK", "type": "Other"})
    return added


def _entities_from_propn_tokens(doc, existing_keys: set[str]) -> list[dict[str, Any]]:
    """Catch proper nouns spaCy didn't group into ents/chunks."""
    added = []
    i = 0
    while i < len(doc):
        tok = doc[i]
        if tok.pos_ == "PROPN" and not tok.is_space:
            end = i + 1
            while end < len(doc) and doc[end].pos_ == "PROPN":
                end += 1
            text = clean_span_text(doc[i:end].text)
            if len(text) >= 2:
                k = text.lower()
                if k not in existing_keys:
                    existing_keys.add(k)
                    added.append({"text": text, "label": "PROPN", "type": "Other"})
            i = end
        else:
            i += 1
    return added


def _ordered_entity_spans_in_sent(
    sent, keys_to_text: dict[str, str]
) -> list[str]:
    """Order of first mention per entity key within sentence."""
    found: list[tuple[int, str]] = []
    seen_local = set()
    for ent in sent.doc.ents:
        if ent.sent != sent:
            continue
        name = clean_span_text(ent.text)
        k = name.lower()
        if k in keys_to_text and k not in seen_local:
            seen_local.add(k)
            found.append((ent.start_char, keys_to_text[k]))
    try:
        for nc in sent.doc.noun_chunks:
            if nc.sent != sent:
                continue
            name = clean_span_text(nc.text)
            k = name.lower()
            if k in keys_to_text and k not in seen_local:
                seen_local.add(k)
                found.append((nc.start_char, keys_to_text[k]))
    except ValueError:
        pass
    found.sort(key=lambda x: x[0])
    return [t for _, t in found]


def _add_cooccurrence_fallback(
    doc,
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(entities) < 2:
        return relations
    # Avoid cluttering when we already extracted structured relations
    if len(relations) > 0:
        return relations
    keys_to_text = {e["text"].lower(): e["text"] for e in entities}
    seen: set[tuple] = set()

    for sent in doc.sents:
        ordered = _ordered_entity_spans_in_sent(sent, keys_to_text)
        if len(ordered) < 2:
            continue
        for a, b in zip(ordered[:-1], ordered[1:]):
            if a.lower() == b.lower():
                continue
            k = _relation_key(a, b, "related_to")
            if k in seen:
                continue
            seen.add(k)
            relations.append(
                {"source": a, "target": b, "relation": "related_to", "passive": False}
            )
    return relations


def _entities_from_content_tokens(
    doc,
    existing_keys: set[str],
    max_nodes: int = 32,
) -> list[dict[str, Any]]:
    """If NER/chunks miss (informal text), use substantive tokens as nodes."""
    added = []
    skip_pos = ("DET", "PRON", "ADP", "CCONJ", "SCONJ", "AUX", "PART", "PUNCT", "SPACE", "NUM")
    candidates: list[tuple[int, str, str]] = []
    for tok in doc:
        if tok.is_space or tok.pos_ in skip_pos:
            continue
        t = clean_span_text(tok.text)
        if len(t) < 3:
            continue
        k = t.lower()
        if k in existing_keys:
            continue
        if tok.is_alpha and tok.pos_ in ("NOUN", "VERB", "ADJ", "PROPN", "X"):
            lab = "PROPN" if tok.pos_ == "PROPN" else "TOKEN"
            candidates.append((len(t), k, t, lab))
    candidates.sort(key=lambda x: -x[0])
    seen_run: set[str] = set()
    for _score, k, t, lab in candidates:
        if len(added) >= max_nodes:
            break
        if k in seen_run:
            continue
        seen_run.add(k)
        existing_keys.add(k)
        added.append({"text": t, "label": lab, "type": "Other"})
    return added


def _add_pairwise_fallback(
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """If still no edges, connect entity list in order (document NER order)."""
    if relations or len(entities) < 2:
        return relations
    seen = set()
    out = list(relations)
    for a, b in zip(entities[:-1], entities[1:]):
        sa, sb = a["text"], b["text"]
        if sa.lower() == sb.lower():
            continue
        k = _relation_key(sa, sb, "mentioned_with")
        if k in seen:
            continue
        seen.add(k)
        out.append(
            {
                "source": sa,
                "target": sb,
                "relation": "mentioned_with",
                "passive": False,
            }
        )
    return out


def extract(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {"entities": [], "relations": [], "sentences": []}

    nlp = get_nlp()
    doc = nlp(text)

    all_entities, keys = _entities_from_ner(doc)
    all_entities.extend(_entities_from_noun_chunks(doc, keys))
    all_entities.extend(_entities_from_propn_tokens(doc, keys))
    if not all_entities:
        all_entities.extend(_entities_from_content_tokens(doc, keys))

    # Dedupe by lower key preserving first label
    by_lower: dict[str, dict] = {}
    for e in all_entities:
        k = e["text"].lower()
        if k not in by_lower:
            by_lower[k] = e
    all_entities = list(by_lower.values())

    if not all_entities and text:
        snippet = clean_span_text(text)[:120]
        if snippet:
            all_entities = [{"text": snippet, "label": "DOCUMENT", "type": "Other"}]

    all_relations: list[dict] = []
    for sent in doc.sents:
        all_relations.extend(extract_relations_from_sentence(sent, doc))

    all_relations = _drop_low_value_relations(all_relations)
    all_relations = _add_cooccurrence_fallback(doc, all_entities, all_relations)
    all_relations = _add_pairwise_fallback(all_entities, all_relations)

    sentences = [clean_span_text(s.text) for s in doc.sents]

    # Enhance with Gemini API if available
    if gemini_config.gemini_config.is_available():
        try:
            enhanced_result = gemini_config.gemini_config.enhance_extraction_with_gemini(
                all_entities, all_relations, text
            )
            
            # Use enhanced results if successful
            if enhanced_result.get("enhanced", False):
                all_entities = enhanced_result.get("entities", all_entities)
                all_relations = enhanced_result.get("relations", all_relations)
                
                # Add enhancement info to sentences
                if enhanced_result.get("gemini_entities", 0) > 0:
                    sentences.append(f"[Gemini enhanced: +{enhanced_result['gemini_entities']} entities, +{enhanced_result.get('gemini_relations', 0)} relations]")
            
        except Exception as e:
            # Log error but continue with spaCy results
            sentences.append(f"[Gemini enhancement failed: {str(e)}]")

    return {
        "entities": all_entities,
        "relations": all_relations,
        "sentences": sentences,
    }
