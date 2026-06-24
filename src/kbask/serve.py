"""MCP stdio server entry point.

Registers structural, semantic, and hybrid tools and serves them over
stdio JSON-RPC 2.0. Designed to be host-agnostic — works with Claude
Code, Codex, Gemini CLI, and any other MCP-compatible client.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict

from kbask import state
from kbask.backends import graphify as _graphify_backend
from kbask.backends import understand as _understand_backend
from kbask.tools import hybrid, semantic, structural


def _reload(target: str = "all") -> Dict[str, Any]:
    """Drop in-process caches so the next tool call re-reads from disk."""
    target = (target or "all").lower()
    if target not in {"all", "structural", "semantic"}:
        return {"error": f"unknown target {target!r}; expected all|structural|semantic"}

    cleared: Dict[str, Any] = {}
    if target in {"all", "structural"}:
        cleared["structural"] = _graphify_backend.clear_cache()
    if target in {"all", "semantic"}:
        cleared["semantic"] = _understand_backend.clear_cache()

    try:
        graph_path = state.graph_path()
        graph_mtime = graph_path.stat().st_mtime_ns if graph_path.exists() else None
    except RuntimeError:
        graph_mtime = None
    try:
        kg_path = state.knowledge_graph_path()
        kg_mtime = kg_path.stat().st_mtime_ns if kg_path.exists() else None
    except RuntimeError:
        kg_mtime = None

    return {
        "target": target,
        "cleared": cleared,
        "graph_mtime_ns": graph_mtime,
        "knowledge_graph_mtime_ns": kg_mtime,
    }


logger = logging.getLogger("kbask.serve")


# Tool registry: name -> (handler, jsonschema input spec, description).
# Schemas are intentionally permissive at this stage; tighten before 1.0.
_TOOLS: Dict[str, Dict[str, Any]] = {
    "query_graph": {
        "fn": structural.query_graph,
        "description": "BFS/DFS keyword search over the structural code graph.",
        "input": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "depth": {"type": "integer", "default": 3, "minimum": 1, "maximum": 6},
                "mode": {"type": "string", "enum": ["bfs", "dfs"], "default": "bfs"},
                "token_budget": {"type": "integer", "default": 2000},
            },
            "required": ["question"],
        },
    },
    "get_node": {
        "fn": structural.get_node,
        "description": "Look up a single node by label or ID.",
        "input": {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
        },
    },
    "get_neighbors": {
        "fn": structural.get_neighbors,
        "description": "First-hop neighbors of a node.",
        "input": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "relation_filter": {"type": "string"},
                "depth": {"type": "integer", "default": 1, "minimum": 1, "maximum": 3},
            },
            "required": ["label"],
        },
    },
    "get_community": {
        "fn": structural.get_community,
        "description": "Members of a Louvain community.",
        "input": {
            "type": "object",
            "properties": {"community_id": {"type": "integer"}},
            "required": ["community_id"],
        },
    },
    "god_nodes": {
        "fn": structural.god_nodes,
        "description": "Highest-centrality nodes (architectural hot spots).",
        "input": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 20}},
        },
    },
    "graph_stats": {
        "fn": structural.graph_stats,
        "description": "Graph counts, density, and top communities.",
        "input": {"type": "object", "properties": {}},
    },
    "shortest_path": {
        "fn": structural.shortest_path,
        "description": "Shortest path between two nodes.",
        "input": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
                "max_hops": {"type": "integer", "default": 8, "minimum": 1, "maximum": 20},
            },
            "required": ["source", "target"],
        },
    },
    "semantic_explain": {
        "fn": semantic.semantic_explain,
        "description": "Narrative explanation for a file path or symbol.",
        "input": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        },
    },
    "semantic_chat": {
        "fn": semantic.semantic_chat,
        "description": "Free-form question against the semantic knowledge graph.",
        "input": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "scope": {"type": "string"},
            },
            "required": ["question"],
        },
    },
    "semantic_diff": {
        "fn": semantic.semantic_diff,
        "description": "Explain what a git diff changes and why.",
        "input": {
            "type": "object",
            "properties": {
                "base": {"type": "string"},
                "head": {"type": "string", "default": "HEAD"},
            },
            "required": ["base"],
        },
    },
    "semantic_onboard": {
        "fn": semantic.semantic_onboard,
        "description": "Onboarding guide for a module or directory.",
        "input": {
            "type": "object",
            "properties": {"area": {"type": "string"}},
            "required": ["area"],
        },
    },
    "semantic_domain": {
        "fn": semantic.semantic_domain,
        "description": "Business-domain map for the repo or a sub-area.",
        "input": {
            "type": "object",
            "properties": {"area": {"type": "string"}},
        },
    },
    "ask": {
        "fn": hybrid.ask,
        "description": "Hybrid: structural BFS for a question, with semantic narrative on top candidates.",
        "input": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
            "required": ["question"],
        },
    },
    "trace": {
        "fn": hybrid.trace,
        "description": "Hybrid: shortest path between two nodes with semantic gloss per hop.",
        "input": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
            },
            "required": ["source", "target"],
        },
    },
    "onboard": {
        "fn": hybrid.onboard,
        "description": "Hybrid: community detection in an area + per-community domain knowledge.",
        "input": {
            "type": "object",
            "properties": {"area": {"type": "string"}},
            "required": ["area"],
        },
    },
    "reload": {
        "fn": _reload,
        "description": (
            "Drop in-process caches so the next call re-reads kbask-out/ from disk. "
            "Use after running `kbask update` against this repo from another shell. "
            "target=all|structural|semantic (default all)."
        ),
        "input": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "all | structural | semantic (default all).",
                    "default": "all",
                },
            },
        },
    },
}


def run(out_dir: Path) -> int:
    """Entry point for `kbask serve <out_dir>`. Routes to the MCP stdio server."""
    # Log to stderr — stdout is sacred (JSON-RPC frames live there).
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="kbask: %(message)s")

    state.set_out_dir(out_dir)
    if not out_dir.exists():
        logger.warning("kbask-out directory %s does not exist; serving in degraded mode", out_dir)

    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import TextContent, Tool
    except ImportError as exc:
        logger.error("mcp package not installed: %s", exc)
        return 1

    server: "Server" = Server("kbask")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(name=name, description=spec["description"], inputSchema=spec["input"])
            for name, spec in _TOOLS.items()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> list[TextContent]:
        from kbask import tokens
        from kbask.backends.graphify import GraphifyUnavailable
        from kbask.backends.understand import UnderstandUnavailable

        input_text = json.dumps(arguments or {}, default=str)

        def _wrap(payload: Any) -> str:
            body = json.dumps(payload, default=str)
            annotated = tokens.annotate(payload, input_text=input_text, output_text=body, tool=name)
            return json.dumps(annotated, default=str)

        spec = _TOOLS.get(name)
        if spec is None:
            return [TextContent(type="text", text=_wrap({"error": f"unknown tool: {name}"}))]
        handler: Callable[..., Any] = spec["fn"]
        try:
            result = handler(**(arguments or {}))
        except NotImplementedError as exc:
            return [TextContent(type="text", text=_wrap({"error": str(exc), "tool": name}))]
        except (GraphifyUnavailable, UnderstandUnavailable) as exc:
            return [TextContent(type="text", text=_wrap({"error": str(exc), "tool": name, "backend": exc.__class__.__name__}))]
        except Exception as exc:
            logger.exception("tool %s failed", name)
            return [TextContent(type="text", text=_wrap({"error": str(exc), "tool": name}))]
        return [TextContent(type="text", text=_wrap(result))]

    async def _main() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(_main())
    return 0
