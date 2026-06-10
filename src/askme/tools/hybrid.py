"""Hybrid MCP tools that compose Graphify + Understand-Anything.

The value proposition of askme lives here. Each hybrid tool returns a
structured bundle: structural facts on the left, semantic narrative on
the right. The calling agent's LLM does the synthesis.
"""

from __future__ import annotations

from typing import Any, Dict

from askme.backends import graphify, understand


def ask(question: str, top_k: int = 5) -> Dict[str, Any]:
    """Run a structural BFS for `question`, then attach semantic narrative for the top hits.

    Returns:
      {
        "structural": <graphify.query_graph result>,
        "semantic": [<understand.explain bundle for each candidate>],
        "join_key": "(file_path, line)"
      }
    """
    raise NotImplementedError(
        "askme: hybrid.ask not yet wired. Will combine graphify.query_graph "
        "with understand.semantic_explain on top candidates."
    )


def trace(source: str, target: str) -> Dict[str, Any]:
    """Shortest path from source to target with a semantic gloss per hop."""
    raise NotImplementedError("askme: hybrid.trace not yet wired.")


def onboard(area: str) -> Dict[str, Any]:
    """Community detection in `area` + per-community domain knowledge."""
    raise NotImplementedError("askme: hybrid.onboard not yet wired.")
