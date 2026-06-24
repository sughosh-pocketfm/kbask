"""Graphify backend.

The Graphify Python package (`graphifyy` on PyPI, importable as `graphify`)
ships a fully built MCP server in `graphify.serve`. We reuse its internal
helpers (`_load_graph`, `_score_nodes`, `_bfs`, `_dfs`, ...) instead of
duplicating the traversal logic. These are prefixed with `_` but they
form a stable internal API in practice; we pin the dependency to track it.

For the `update` command we shell out to the `graphify` CLI so we inherit
its file-discovery, tree-sitter, and community-detection logic unchanged.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from kbask import state


class GraphifyUnavailable(RuntimeError):
    pass


# ------------------------------------------------------------------
# Version / availability
# ------------------------------------------------------------------

def version() -> str:
    try:
        module = importlib.import_module("graphify")
        return getattr(module, "__version__", "unknown")
    except ImportError:
        return "not-installed"


# ------------------------------------------------------------------
# Update (delegates to graphify CLI)
# ------------------------------------------------------------------

def update(repo: Path, graph_path: Path) -> None:
    """Run `graphify update .` in `repo` and place the output at `graph_path`."""
    cli = shutil.which("graphify")
    if cli is None:
        uvx = shutil.which("uvx")
        if uvx is None:
            raise GraphifyUnavailable(
                "Neither 'graphify' nor 'uvx' found on PATH. "
                "Install with: uv tool install graphifyy"
            )
        cmd = [uvx, "--from", "graphifyy", "graphify", "update", "."]
    else:
        cmd = [cli, "update", "."]

    proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    if proc.returncode != 0:
        raise GraphifyUnavailable(
            f"graphify update failed (rc={proc.returncode}):\n{proc.stderr}"
        )

    default_output = repo / "graphify-out" / "graph.json"
    if not default_output.exists():
        raise GraphifyUnavailable(
            f"graphify completed but graph.json not found at {default_output}"
        )

    graph_path.parent.mkdir(parents=True, exist_ok=True)
    if default_output.resolve() != graph_path.resolve():
        graph_path.write_bytes(default_output.read_bytes())


# ------------------------------------------------------------------
# Graph state (lazy-loaded)
# ------------------------------------------------------------------

_graph_cache: Dict[str, Any] = {}


def clear_cache() -> Dict[str, Any]:
    """Drop the in-process graph cache. Next call re-reads from disk."""
    had_key = _graph_cache.get("key")
    _graph_cache.clear()
    return {"cleared": bool(had_key), "previous_key": had_key}


def _load() -> Dict[str, Any]:
    """Load (or reload on path change) the networkx graph + communities."""
    path = state.graph_path()
    if not path.exists():
        raise GraphifyUnavailable(
            f"graph.json not found at {path}. Run `kbask update <repo>` first."
        )
    key = str(path.resolve()) + ":" + str(path.stat().st_mtime_ns)
    if _graph_cache.get("key") == key:
        return _graph_cache

    try:
        from graphify import serve as gs  # type: ignore[import-not-found]
    except ImportError as exc:
        raise GraphifyUnavailable(
            "graphifyy not installed in this environment. "
            "Install via `uv pip install graphifyy` or the kbask-mcp extras."
        ) from exc

    G = gs._load_graph(str(path))
    communities = gs._communities_from_graph(G)
    _graph_cache.clear()
    _graph_cache.update({"key": key, "G": G, "communities": communities, "gs": gs})
    return _graph_cache


def _label(d: Dict[str, Any], nid: str) -> str:
    return d.get("label") or nid


def _find_nodes(G, query: str, limit: int = 25) -> List[str]:
    """Rank-ordered node lookup tolerant of labels, IDs, file paths, and basenames.

    Strategies, in priority order:
      1. exact id match
      2. exact label match (case-insensitive)
      3. exact source_file match
      4. source_file endswith (handles partial paths like
         "fmadsclient/data/source/FmAdsLocalDataSource.kt")
      5. basename match on source_file
      6. substring match on label
      7. substring match on nid
      8. graphify's diacritic-insensitive score (norm_label / id)
    """
    needle = query.strip()
    if not needle:
        return []
    nlow = needle.lower()
    basename = needle.split("/")[-1].lower()

    exact_id: List[str] = []
    exact_label: List[str] = []
    exact_src: List[str] = []
    suffix_src: List[str] = []
    basename_src: List[str] = []
    sub_label: List[str] = []
    sub_id: List[str] = []

    for nid, d in G.nodes(data=True):
        nid_low = nid.lower()
        label_low = (d.get("label") or "").lower()
        src = (d.get("source_file") or "")
        src_low = src.lower()

        if nid_low == nlow:
            exact_id.append(nid)
            continue
        if label_low == nlow:
            exact_label.append(nid)
            continue
        if src_low == nlow:
            exact_src.append(nid)
            continue
        if src and src_low.endswith(nlow) and "/" in nlow:
            suffix_src.append(nid)
            continue
        if src and src_low.split("/")[-1] == basename:
            basename_src.append(nid)
            continue
        if label_low and nlow in label_low:
            sub_label.append(nid)
            continue
        if nlow in nid_low:
            sub_id.append(nid)

    ordered: List[str] = []
    for bucket in (exact_id, exact_label, exact_src, suffix_src, basename_src, sub_label, sub_id):
        for nid in bucket:
            if nid not in ordered:
                ordered.append(nid)
                if len(ordered) >= limit:
                    return ordered

    # Fallback to graphify's scored matcher for fuzzy / diacritic cases.
    try:
        from graphify import serve as gs  # type: ignore[import-not-found]
        for _, nid in gs._score_nodes(G, [t for t in nlow.split() if len(t) > 2]):
            if nid not in ordered:
                ordered.append(nid)
            if len(ordered) >= limit:
                break
    except Exception:
        pass
    return ordered


# ------------------------------------------------------------------
# MCP tool surface — return dict bundles (host LLM synthesizes)
# ------------------------------------------------------------------

def query_graph(question: str, depth: int = 3, mode: str = "bfs", token_budget: int = 2000) -> Dict[str, Any]:
    cache = _load()
    G, gs = cache["G"], cache["gs"]
    terms = [t.lower() for t in question.split() if len(t) > 2]
    scored = gs._score_nodes(G, terms)
    starts = [nid for _, nid in scored[:3]]
    if not starts:
        return {"matches": [], "text": "No matching nodes found.", "starts": []}
    depth = max(1, min(int(depth), 6))
    nodes, edges = (gs._dfs(G, starts, depth) if mode == "dfs" else gs._bfs(G, starts, depth))
    text = gs._subgraph_to_text(G, nodes, edges, int(token_budget))
    return {
        "mode": mode,
        "depth": depth,
        "starts": [{"id": n, "label": _label(G.nodes[n], n)} for n in starts],
        "node_count": len(nodes),
        "edge_count": len(edges),
        "text": text,
    }


def get_node(label: str) -> Dict[str, Any]:
    cache = _load()
    G = cache["G"]
    nids = _find_nodes(G, label, limit=10)
    if not nids:
        return {"error": f"no node matching {label!r}"}
    nid = nids[0]
    d = G.nodes[nid]
    out = {
        "id": nid,
        "label": _label(d, nid),
        "source_file": d.get("source_file", ""),
        "source_location": d.get("source_location", ""),
        "file_type": d.get("file_type", ""),
        "community": d.get("community", None),
        "degree": G.degree(nid),
    }
    if len(nids) > 1:
        out["other_matches"] = [
            {"id": n, "label": _label(G.nodes[n], n), "source_file": G.nodes[n].get("source_file", "")}
            for n in nids[1:6]
        ]
    return out


def get_neighbors(label: str, relation_filter: Optional[str] = None, depth: int = 1) -> Dict[str, Any]:
    cache = _load()
    G = cache["G"]
    matches = _find_nodes(G, label, limit=5)
    if not matches:
        return {"error": f"no node matching {label!r}", "neighbors": []}
    nid = matches[0]
    rel_filter = (relation_filter or "").lower()
    out: List[Dict[str, Any]] = []
    for n in G.neighbors(nid):
        ed = G.edges[nid, n]
        rel = ed.get("relation", "")
        if rel_filter and rel_filter not in rel.lower():
            continue
        out.append({
            "id": n,
            "label": _label(G.nodes[n], n),
            "relation": rel,
            "confidence": ed.get("confidence", ""),
        })
    bundle: Dict[str, Any] = {
        "node": {"id": nid, "label": _label(G.nodes[nid], nid),
                 "source_file": G.nodes[nid].get("source_file", "")},
        "neighbors": out,
    }
    if len(matches) > 1:
        bundle["other_matches"] = [
            {"id": n, "label": _label(G.nodes[n], n), "source_file": G.nodes[n].get("source_file", "")}
            for n in matches[1:5]
        ]
    return bundle


def get_community(community_id: int) -> Dict[str, Any]:
    cache = _load()
    G, communities = cache["G"], cache["communities"]
    nodes = communities.get(int(community_id), [])
    if not nodes:
        return {"error": f"community {community_id} not found", "members": []}
    return {
        "community_id": int(community_id),
        "size": len(nodes),
        "members": [
            {"id": n, "label": _label(G.nodes[n], n), "source_file": G.nodes[n].get("source_file", "")}
            for n in nodes
        ],
    }


def god_nodes(top_n: int = 10, limit: Optional[int] = None) -> Dict[str, Any]:
    # Accept either `top_n` (graphify convention) or `limit` (kbask schema).
    cache = _load()
    G = cache["G"]
    from graphify.analyze import god_nodes as _god  # type: ignore[import-not-found]
    n = int(limit if limit is not None else top_n)
    return {"god_nodes": _god(G, top_n=n)}


def graph_stats() -> Dict[str, Any]:
    cache = _load()
    G, communities = cache["G"], cache["communities"]
    confs = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
    total = len(confs) or 1
    def pct(label: str) -> int:
        return round(confs.count(label) / total * 100)
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "communities": len(communities),
        "confidence_pct": {
            "EXTRACTED": pct("EXTRACTED"),
            "INFERRED": pct("INFERRED"),
            "AMBIGUOUS": pct("AMBIGUOUS"),
        },
    }


def shortest_path(source: str, target: str, max_hops: int = 8) -> Dict[str, Any]:
    cache = _load()
    G = cache["G"]
    try:
        import networkx as nx  # type: ignore[import-not-found]
    except ImportError as exc:
        raise GraphifyUnavailable("networkx not installed") from exc

    src_matches = _find_nodes(G, source, limit=3)
    tgt_matches = _find_nodes(G, target, limit=3)
    if not src_matches:
        return {"error": f"no node matching source {source!r}"}
    if not tgt_matches:
        return {"error": f"no node matching target {target!r}"}
    src_nid, tgt_nid = src_matches[0], tgt_matches[0]
    try:
        path = nx.shortest_path(G, src_nid, tgt_nid)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return {"error": "no path", "source": src_nid, "target": tgt_nid}
    hops = len(path) - 1
    if hops > int(max_hops):
        return {"error": f"path exceeds max_hops={max_hops}", "hops": hops}

    segments: List[Dict[str, Any]] = []
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        ed = G.edges[u, v]
        segments.append({
            "from": {"id": u, "label": _label(G.nodes[u], u), "source_file": G.nodes[u].get("source_file", "")},
            "to": {"id": v, "label": _label(G.nodes[v], v), "source_file": G.nodes[v].get("source_file", "")},
            "relation": ed.get("relation", ""),
            "confidence": ed.get("confidence", ""),
        })
    return {"hops": hops, "path": segments}
