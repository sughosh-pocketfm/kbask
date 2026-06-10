---
description: Query the kbask MCP server — structural + semantic code knowledge for this repo.
---

You have access to the **kbask** MCP server. It joins Graphify's structural
code graph with Understand-Anything's semantic knowledge graph. Use it to
answer the user's question about this repo.

## Tool routing

Pick the smallest tool that answers the question. Do not chain unless needed.

| User intent | First tool |
|---|---|
| "how does X work?" / "explain X" | `kbask.ask` (hybrid: structural -> semantic -> file fallback) |
| "trace flow from A to B" / "what calls Y" | `kbask.trace` |
| "onboard me to module Z" / "tour the auth area" | `kbask.onboard` |
| Need a single file/symbol explanation | `kbask.semantic_explain` |
| Need raw edges, neighbors, paths | `kbask.query_graph` / `kbask.get_neighbors` / `kbask.shortest_path` |
| Need repo stats / hot spots | `kbask.graph_stats` / `kbask.god_nodes` |

`kbask.ask` does a three-stage cascade for broad questions:
1. Structural BFS via graphify.
2. If the structural result was too broad, semantic chat via understand-anything.
3. If both miss, file-path candidates that the caller LLM should Read directly.

Inspect `stages_used` in the response to know which stages fired.

## Rules

1. Always cite file paths returned by kbask (format: `path/to/file.kt:line` when line is known).
2. Do not invent symbols — if a tool returns no match, say so and try the next-broader tool.
3. Keep results scoped to what the user asked. Don't dump full graphs.
4. If the user's input is `$ARGUMENTS`, use it as the kbask question argument.

## User question

$ARGUMENTS
