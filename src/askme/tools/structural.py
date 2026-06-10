"""MCP tool registrations for structural (Graphify) queries.

Each function here is wrapped as an MCP tool in askme.serve. Handlers are
intentionally thin — they delegate to askme.backends.graphify which reuses
the upstream Graphify traversal helpers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from askme.backends import graphify


def query_graph(question: str, depth: int = 3, mode: str = "bfs", token_budget: int = 2000) -> Dict[str, Any]:
    return graphify.query_graph(question=question, depth=depth, mode=mode, token_budget=token_budget)


def get_node(label: str) -> Dict[str, Any]:
    return graphify.get_node(label=label)


def get_neighbors(label: str, relation_filter: Optional[str] = None, depth: int = 1) -> Dict[str, Any]:
    return graphify.get_neighbors(label=label, relation_filter=relation_filter, depth=depth)


def get_community(community_id: int) -> Dict[str, Any]:
    return graphify.get_community(community_id=community_id)


def god_nodes(top_n: int = 10, limit: Optional[int] = None) -> Dict[str, Any]:
    return graphify.god_nodes(top_n=top_n, limit=limit)


def graph_stats() -> Dict[str, Any]:
    return graphify.graph_stats()


def shortest_path(source: str, target: str, max_hops: int = 8) -> Dict[str, Any]:
    return graphify.shortest_path(source=source, target=target, max_hops=max_hops)
