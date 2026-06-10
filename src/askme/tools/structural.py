"""MCP tool registrations for structural (Graphify) queries.

Each function here is wrapped as an MCP tool in askme.serve. Handlers are
intentionally thin — they delegate to askme.backends.graphify and rely on
the upstream Graphify implementations for actual graph traversal.
"""

from __future__ import annotations

from typing import Any, Dict

from askme.backends import graphify


def query_graph(question: str, depth: int = 3, mode: str = "bfs", token_budget: int = 2000) -> Dict[str, Any]:
    return graphify.query_graph(question=question, depth=depth, mode=mode, token_budget=token_budget)


def get_node(label: str) -> Dict[str, Any]:
    return graphify.get_node(label=label)


def get_neighbors(label: str, depth: int = 1) -> Dict[str, Any]:
    return graphify.get_neighbors(label=label, depth=depth)


def get_community(community_id: int) -> Dict[str, Any]:
    return graphify.get_community(community_id=community_id)


def god_nodes(limit: int = 20) -> Dict[str, Any]:
    return graphify.god_nodes(limit=limit)


def graph_stats() -> Dict[str, Any]:
    return graphify.graph_stats()


def shortest_path(source: str, target: str) -> Dict[str, Any]:
    return graphify.shortest_path(source=source, target=target)
