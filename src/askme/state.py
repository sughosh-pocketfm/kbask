"""Process-wide state for the askme MCP server.

The MCP server runs as a long-lived process. Tool handlers need access
to the active out-dir (which holds graph.json + knowledge-graph.json)
without threading it through every call. This module owns that state.

`serve.run` is the only writer; everything else reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


_out_dir: Optional[Path] = None


def set_out_dir(path: Path) -> None:
    global _out_dir
    _out_dir = path.resolve()


def out_dir() -> Path:
    if _out_dir is None:
        raise RuntimeError(
            "askme: state.out_dir not initialized. "
            "Set it via state.set_out_dir() before invoking any tool."
        )
    return _out_dir


def graph_path() -> Path:
    return out_dir() / "graph.json"


def knowledge_graph_path() -> Path:
    return out_dir() / "knowledge-graph.json"


def meta_path() -> Path:
    return out_dir() / "meta.json"
