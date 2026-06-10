"""Graphify backend.

Imports the `graphifyy` package directly when available so we don't pay
subprocess overhead per MCP call. Falls back to `uvx --from graphifyy ...`
subprocesses for the `update` command, which we keep delegating to the
upstream CLI to avoid duplicating its file-discovery + tree-sitter logic.
"""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


class GraphifyUnavailable(RuntimeError):
    pass


def version() -> str:
    try:
        module = importlib.import_module("graphify")
        return getattr(module, "__version__", "unknown")
    except ImportError:
        return "not-installed"


def update(repo: Path, graph_path: Path) -> None:
    """Run `graphify update .` and ensure the output lands at graph_path."""
    cli = shutil.which("graphify")
    if cli is None:
        uvx = shutil.which("uvx")
        if uvx is None:
            raise GraphifyUnavailable(
                "Neither 'graphify' nor 'uvx' was found on PATH. "
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


def load_graph(graph_path: Path) -> Dict[str, Any]:
    return json.loads(graph_path.read_text(encoding="utf-8"))


# --- MCP tool surface ----------------------------------------------------
#
# The Graphify MCP server exposes seven tools (query_graph, get_node,
# get_neighbors, get_community, god_nodes, graph_stats, shortest_path).
# We re-export them as Python callables that operate on a loaded graph
# dict so tools/structural.py can wrap them as MCP tool handlers without
# additional subprocess hops.
#
# TODO: bind these to the upstream implementations in graphify.serve.
# For now they raise NotImplementedError so MCP `tools/list` works while
# we wire up real handlers.


def _not_implemented(name: str) -> "Any":
    def stub(*_: object, **__: object) -> Any:
        raise NotImplementedError(
            f"askme: graphify.{name} handler not yet wired. "
            f"Run `askme health` to check backend state."
        )

    return stub


query_graph = _not_implemented("query_graph")
get_node = _not_implemented("get_node")
get_neighbors = _not_implemented("get_neighbors")
get_community = _not_implemented("get_community")
god_nodes = _not_implemented("god_nodes")
graph_stats = _not_implemented("graph_stats")
shortest_path = _not_implemented("shortest_path")
