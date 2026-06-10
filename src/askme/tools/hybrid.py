"""Hybrid MCP tools that compose Graphify + Understand-Anything.

The value proposition of askme lives here. Each hybrid tool returns a
structured bundle: structural facts on one side, semantic narrative on
the other. The calling agent's LLM does the synthesis — askme never
calls a model itself.
"""

from __future__ import annotations

from typing import Any, Dict, List

from askme.backends import graphify, understand


def _node_source_files(struct_result: Dict[str, Any]) -> List[str]:
    """Pull source_file hints out of a structural result, deduplicated, order-preserved."""
    seen: Dict[str, None] = {}
    for n in struct_result.get("starts", []):
        path = n.get("source_file") or n.get("label")
        if isinstance(path, str) and path not in seen:
            seen[path] = None
    return list(seen)


def ask(question: str, top_k: int = 5) -> Dict[str, Any]:
    """Run a structural BFS for `question`, then attach semantic narrative for the top hits."""
    try:
        struct = graphify.query_graph(question=question, depth=3, mode="bfs", token_budget=2000)
    except graphify.GraphifyUnavailable as exc:
        return {"error": str(exc), "stage": "structural"}

    starts = struct.get("starts", [])[: int(top_k)]
    semantic: List[Dict[str, Any]] = []
    for s in starts:
        target = s.get("label") or s.get("id")
        if not target:
            continue
        try:
            semantic.append({"target": target, "explain": understand.semantic_explain(target=target)})
        except understand.UnderstandUnavailable as exc:
            semantic.append({"target": target, "error": str(exc)})
    return {
        "question": question,
        "structural": struct,
        "semantic": semantic,
        "join_key": "node.label",
    }


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
        gloss = None
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
