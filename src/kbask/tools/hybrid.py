"""Hybrid MCP tools that compose Graphify + Understand-Anything.

The value proposition of kbask lives here. Each hybrid tool returns a
structured bundle: structural facts on one side, semantic narrative on
the other. The calling agent's LLM does the synthesis — kbask never
calls a model itself.

`ask()` runs a three-stage cascade:
  1. graphify.query_graph (cheap, exact)
  2. understand.semantic_chat (semantic, when structural is too broad)
  3. file-candidates fallback (filename grep + read-source hint) so the
     caller LLM can do its own analysis when both indexes miss

Each stage is tagged in the response so the caller knows what fired.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from kbask.backends import graphify, understand


# A structural result is "broad" when no clear starts were found OR the
# return scope blew past this many distinct nodes — i.e. the BFS hit a
# god-node cluster and the answer is buried in noise.
BROAD_NODE_THRESHOLD = 80


def _node_source_files(struct_result: Dict[str, Any]) -> List[str]:
    """Pull source_file hints out of a structural result, deduplicated, order-preserved."""
    seen: Dict[str, None] = {}
    for n in struct_result.get("starts", []):
        path = n.get("source_file") or n.get("label")
        if isinstance(path, str) and path not in seen:
            seen[path] = None
    return list(seen)


def _is_broad(struct_result: Dict[str, Any]) -> bool:
    if not struct_result.get("starts"):
        return True
    nc = int(struct_result.get("node_count") or 0)
    return nc == 0 or nc > BROAD_NODE_THRESHOLD


def _file_candidates(question: str, limit: int = 12) -> List[Dict[str, Any]]:
    """Filename grep against the structural graph as last-resort fallback.

    Returns file-node hits whose path contains any term from `question`.
    The caller LLM can then Read these files directly.
    """
    try:
        cache = graphify._load()
    except graphify.GraphifyUnavailable:
        return []
    G = cache["G"]
    terms = [t.lower() for t in question.split() if len(t) > 2]
    if not terms:
        return []
    scored: List[tuple[int, str, str]] = []
    for nid, d in G.nodes(data=True):
        src = (d.get("source_file") or "").lower()
        label = (d.get("label") or "").lower()
        if not src:
            continue
        hits = sum(1 for t in terms if t in src or t in label)
        if hits:
            scored.append((hits, d.get("source_file", ""), d.get("label") or nid))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for hits, path, label in scored:
        if path in seen:
            continue
        seen.add(path)
        out.append({"source_file": path, "label": label, "term_hits": hits})
        if len(out) >= limit:
            break
    return out


def ask(question: str, top_k: int = 5) -> Dict[str, Any]:
    """Three-stage cascade: structural -> semantic -> file candidates.

    Returns a bundle with whatever stages produced useful output and
    `stages_used` so the caller knows which were tried.
    """
    stages_used: List[str] = []
    out: Dict[str, Any] = {"question": question, "join_key": "node.label"}

    # Stage 1: structural BFS
    structural_broad = False
    try:
        struct = graphify.query_graph(question=question, depth=3, mode="bfs", token_budget=2000)
        out["structural"] = struct
        stages_used.append("structural")
        structural_broad = _is_broad(struct)
    except graphify.GraphifyUnavailable as exc:
        out["structural"] = {"error": str(exc)}
        structural_broad = True

    # Stage 1b: semantic_explain on top structural candidates (still cheap)
    if not structural_broad:
        semantic: List[Dict[str, Any]] = []
        for s in (out["structural"].get("starts") or [])[: int(top_k)]:
            target = s.get("label") or s.get("id")
            if not target:
                continue
            try:
                semantic.append({"target": target, "explain": understand.semantic_explain(target=target)})
            except understand.UnderstandUnavailable as exc:
                semantic.append({"target": target, "error": str(exc)})
        out["semantic"] = semantic
        if any("explain" in entry for entry in semantic):
            stages_used.append("semantic_explain")

    # Stage 2: semantic_chat (only when structural didn't narrow well)
    if structural_broad:
        try:
            chat = understand.semantic_chat(question=question)
            out["semantic_chat"] = chat
            if chat.get("matches"):
                stages_used.append("semantic_chat")
            else:
                stages_used.append("semantic_chat:empty")
        except understand.UnderstandUnavailable as exc:
            out["semantic_chat"] = {"error": str(exc)}

    # Stage 3: file-candidates fallback for the caller LLM
    chat_empty = (
        "semantic_chat" not in stages_used
    )
    if structural_broad and chat_empty:
        candidates = _file_candidates(question)
        out["file_candidates"] = candidates
        out["next_steps"] = (
            "Both structural and semantic indexes returned no narrow match. "
            "The caller LLM should read the listed files directly (Read tool) "
            "and grep within them. Consider refining the question with a "
            "module/class/file hint."
        )
        if candidates:
            stages_used.append("file_candidates")
        else:
            stages_used.append("file_candidates:empty")

    out["stages_used"] = stages_used
    return out


def trace(source: str, target: str) -> Dict[str, Any]:
    """Shortest path from source to target with a semantic gloss per hop."""
    try:
        path = graphify.shortest_path(source=source, target=target)
    except graphify.GraphifyUnavailable as exc:
        return {"error": str(exc), "stage": "structural"}

    if "error" in path:
        return {"source": source, "target": target, "structural": path}

    annotated = []
    for seg in path.get("path", []):
        to_label = seg.get("to", {}).get("label")
        gloss: Optional[Dict[str, Any]] = None
        if to_label:
            try:
                gloss = understand.semantic_explain(target=to_label)
            except understand.UnderstandUnavailable as exc:
                gloss = {"error": str(exc)}
        annotated.append({"hop": seg, "gloss": gloss})
    return {"source": source, "target": target, "hops": path.get("hops"), "annotated_path": annotated}


def onboard(area: str) -> Dict[str, Any]:
    """Community detection in `area` + per-community domain knowledge."""
    try:
        struct = graphify.query_graph(question=area, depth=2, mode="bfs", token_budget=1500)
    except graphify.GraphifyUnavailable as exc:
        return {"error": str(exc), "stage": "structural"}

    try:
        sem = understand.semantic_onboard(area=area)
    except understand.UnderstandUnavailable as exc:
        sem = {"error": str(exc)}

    return {"area": area, "structural_map": struct, "semantic_guide": sem}
