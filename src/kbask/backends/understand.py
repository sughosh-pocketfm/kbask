"""Understand-Anything backend.

Understand-Anything is *not* a self-running analyzer. The knowledge graph
is built by an LLM (typically Claude Code) following prompts defined by
the upstream plugin, and persisted to `.understand-anything/knowledge-graph.json`
inside the user's repo.

kbask treats that JSON file as **input data**:

  - `kbask update` copies the latest `.understand-anything/knowledge-graph.json`
    into `kbask-out/knowledge-graph.json` (so MCP queries hit a single dir).
  - MCP semantic tools read the cached copy directly — no Node subprocess,
    no LLM call from inside kbask.

If the user has never run Understand-Anything against the repo, the cache
file is absent and semantic tools return a clear "graph not built" error
pointing them at the right command.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from kbask import state


class UnderstandUnavailable(RuntimeError):
    pass


SOURCE_DIRNAME = ".understand-anything"
GRAPH_FILENAME = "knowledge-graph.json"
META_FILENAME = "meta.json"


# ------------------------------------------------------------------
# Version / availability
# ------------------------------------------------------------------

def version() -> str:
    """Return the knowledge-graph schema version, or 'not-built' if absent."""
    path = state.knowledge_graph_path() if _state_ready() else None
    if path is None or not path.exists():
        return "not-built"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unreadable"
    return str(data.get("version") or data.get("schemaVersion") or "unknown")


def _state_ready() -> bool:
    try:
        state.out_dir()
        return True
    except RuntimeError:
        return False


def is_available() -> bool:
    """Return True iff a usable knowledge-graph.json is present on disk.

    Hybrid tools call this once per request so they can switch to a
    graphify-only fallback (rather than catching UnderstandUnavailable
    on every per-entry call).
    """
    if not _state_ready():
        return False
    path = state.knowledge_graph_path()
    if not path.exists() or path.stat().st_size <= 0:
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict)


# ------------------------------------------------------------------
# Update — copy upstream knowledge graph into our out-dir
# ------------------------------------------------------------------

def update(repo: Path, knowledge_graph_path: Path, dirty: List[str], full_rebuild: bool) -> None:
    """Mirror `<repo>/.understand-anything/knowledge-graph.json` into our cache.

    Incremental rebuilding of the *upstream* graph is owned by Claude Code
    (via the Understand-Anything plugin's auto-update prompt). kbask simply
    refreshes its own copy after the upstream file changes.

    `dirty` and `full_rebuild` are accepted for API parity with the
    structural backend but unused — upstream tracks its own deltas.
    """
    upstream_dir = repo / SOURCE_DIRNAME
    upstream_graph = upstream_dir / GRAPH_FILENAME
    if not upstream_graph.exists():
        raise UnderstandUnavailable(
            f"No knowledge graph at {upstream_graph}. "
            "Run /understand or /understand-update in Claude Code first."
        )
    knowledge_graph_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(upstream_graph, knowledge_graph_path)

    upstream_meta = upstream_dir / META_FILENAME
    if upstream_meta.exists():
        shutil.copy2(upstream_meta, knowledge_graph_path.parent / "knowledge-graph.meta.json")


# ------------------------------------------------------------------
# Lazy load + cache
# ------------------------------------------------------------------

_kg_cache: Dict[str, Any] = {}


def clear_cache() -> Dict[str, Any]:
    """Drop the in-process knowledge-graph cache. Next call re-reads from disk."""
    had_key = _kg_cache.get("key")
    _kg_cache.clear()
    return {"cleared": bool(had_key), "previous_key": had_key}


def _load_kg() -> Dict[str, Any]:
    path = state.knowledge_graph_path()
    if not path.exists():
        raise UnderstandUnavailable(
            f"knowledge-graph.json not found at {path}. "
            "Run `kbask update <repo>` after building it with Understand-Anything."
        )
    key = str(path.resolve()) + ":" + str(path.stat().st_mtime_ns)
    if _kg_cache.get("key") == key:
        return _kg_cache["data"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UnderstandUnavailable(f"knowledge-graph.json malformed: {exc}") from exc
    _kg_cache.clear()
    _kg_cache.update({"key": key, "data": data})
    return data


def _entities(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(data.get("entities") or data.get("nodes") or [])


def _relations(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(data.get("relations") or data.get("edges") or [])


def _files(data: Dict[str, Any]) -> Dict[str, Any]:
    return dict(data.get("files") or {})


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _match_entities(entities: List[Dict[str, Any]], target: str) -> List[Dict[str, Any]]:
    needle = target.lower()
    out: List[Dict[str, Any]] = []
    for e in entities:
        for field in ("id", "name", "label", "qualifiedName", "filePath", "path"):
            val = e.get(field)
            if isinstance(val, str) and needle in val.lower():
                out.append(e)
                break
    return out


def _entities_in_area(entities: List[Dict[str, Any]], area: str) -> List[Dict[str, Any]]:
    needle = area.lower()
    return [
        e for e in entities
        if any(
            isinstance(e.get(f), str) and needle in e[f].lower()
            for f in ("filePath", "path", "module", "package")
        )
    ]


# ------------------------------------------------------------------
# MCP tool surface
# ------------------------------------------------------------------

def semantic_explain(target: str) -> Dict[str, Any]:
    data = _load_kg()
    entities = _entities(data)
    matches = _match_entities(entities, target)
    if not matches:
        files = _files(data)
        file_match = files.get(target) or next(
            (v for k, v in files.items() if target.lower() in k.lower()),
            None,
        )
        if file_match:
            return {"target": target, "kind": "file", "entry": file_match}
        return {"target": target, "matches": [], "error": "no matching entity or file"}
    return {
        "target": target,
        "kind": "entity",
        "matches": matches[:10],
        "total_matches": len(matches),
    }


def semantic_chat(question: str, scope: Optional[str] = None) -> Dict[str, Any]:
    data = _load_kg()
    entities = _entities(data)
    if scope:
        entities = _entities_in_area(entities, scope)
    terms = [t.lower() for t in question.split() if len(t) > 2]
    if not terms:
        return {"question": question, "matches": [], "scope": scope}
    scored: List[tuple] = []
    for e in entities:
        text_blob = " ".join(
            str(e.get(f, "")) for f in ("name", "label", "summary", "description", "purpose")
        ).lower()
        score = sum(text_blob.count(t) for t in terms)
        if score:
            scored.append((score, e))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return {
        "question": question,
        "scope": scope,
        "matches": [e for _, e in scored[:10]],
        "total_matches": len(scored),
    }


def semantic_diff(base: str, head: str = "HEAD") -> Dict[str, Any]:
    # kbask does not run git diff itself — we surface what the host's diff
    # tool found by reading the diff-context entries Understand-Anything
    # writes when /understand-diff has been used. If none, return guidance.
    data = _load_kg()
    diffs = data.get("diffs") or {}
    key = f"{base}..{head}"
    if key in diffs:
        return {"diff": key, "entry": diffs[key]}
    return {
        "diff": key,
        "error": "no precomputed diff entry; run /understand-diff in Claude Code",
        "available_diffs": list(diffs.keys()),
    }


def semantic_onboard(area: str) -> Dict[str, Any]:
    data = _load_kg()
    entities = _entities_in_area(_entities(data), area)
    files = {k: v for k, v in _files(data).items() if area.lower() in k.lower()}
    onboarding = data.get("onboarding") or {}
    area_guide = onboarding.get(area)
    return {
        "area": area,
        "guide": area_guide,
        "entity_count": len(entities),
        "files": files,
        "entities": entities[:30],
    }


def semantic_domain(area: Optional[str] = None) -> Dict[str, Any]:
    data = _load_kg()
    domain = data.get("domain") or {}
    if area:
        # Pick out sub-area if domain map is keyed by area, else filter by area name.
        if isinstance(domain, dict) and area in domain:
            return {"area": area, "domain": domain[area]}
        return {
            "area": area,
            "matches": [
                (k, v) for k, v in (domain.items() if isinstance(domain, dict) else [])
                if area.lower() in k.lower()
            ],
        }
    return {"domain": domain}
