"""Understand-Anything backend.

@understand-anything/core is a Node/TypeScript package, so we communicate
with it via a Node subprocess that imports the package and emits JSON on
stdout. The bridge script is generated at runtime to avoid bundling JS in
the Python wheel.

TODO: ship a small `scripts/bridge.mjs` that exposes the relevant skill
builders (buildChatContext, buildDiffContext, buildExplainContext,
buildOnboardingGuide, etc.) and accepts JSON commands over stdin.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, List, Optional


class UnderstandUnavailable(RuntimeError):
    pass


def version() -> str:
    """Probe @understand-anything/core for its installed version, if reachable."""
    node = shutil.which("node")
    if node is None:
        return "node-not-installed"
    try:
        proc = subprocess.run(
            [node, "-e", "process.stdout.write(require('@understand-anything/core/package.json').version)"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unreachable"
    return proc.stdout.strip() if proc.returncode == 0 else "not-installed"


def update(repo: Path, knowledge_graph_path: Path, dirty: List[str], full_rebuild: bool) -> None:
    """Rebuild knowledge graph entries for the given dirty file set.

    TODO: implement. The shape should be:
      1. Load existing knowledge-graph.json if it exists and not full_rebuild.
      2. Drop entries whose source path is in (dirty + removed).
      3. Spawn `node bridge.mjs analyze` with the file list.
      4. Merge new entries into the carried-over map.
      5. Write knowledge-graph.json.
    """
    raise NotImplementedError(
        "askme: understand-anything update not yet wired. "
        "This will spawn a Node bridge against @understand-anything/core."
    )


# --- MCP tool surface ----------------------------------------------------
#
# Five semantic tools wrap Understand-Anything skill builders. Like the
# Graphify wrappers, these accept primitives and return structured JSON
# (context bundles) for the host agent to reason over — no LLM calls
# happen inside askme.


def _not_implemented(name: str) -> "Any":
    def stub(*_: object, **__: object) -> Any:
        raise NotImplementedError(
            f"askme: understand.{name} handler not yet wired."
        )

    return stub


semantic_explain = _not_implemented("explain")
semantic_chat = _not_implemented("chat")
semantic_diff = _not_implemented("diff")
semantic_onboard = _not_implemented("onboard")
semantic_domain = _not_implemented("domain")
