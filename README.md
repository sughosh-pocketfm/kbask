# askme-mcp

Hybrid MCP server that combines **[Graphify](https://github.com/graphifyy)** (structural code graphs) with **[Understand-Anything](https://github.com/Lum1104/Understand-Anything)** (LLM-derived semantic knowledge bases) into a single MCP endpoint.

Graphify tells you **where** things are. Understand-Anything tells you **why** they exist. `askme` joins both and exposes them as MCP tools usable from Claude Code, Codex, Gemini CLI, and any other MCP-compatible host.

---

## Why a hybrid?

| Backend | Strength | Weakness |
|---|---|---|
| Graphify | Exact, cheap, deterministic AST graph (calls, imports, ownership) | No semantics — doesn't know *why* code exists |
| Understand-Anything | Semantic narrative, domain knowledge, onboarding context | Expensive to build, fuzzy, no edge-precise lookups |

`askme` gives you:

- **All 7 Graphify tools** (`query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`) pass-through
- **5 semantic tools** from Understand-Anything (`semantic_explain`, `semantic_chat`, `semantic_diff`, `semantic_onboard`, `semantic_domain`)
- **Hybrid tools** that compose both:
  - `ask(question)` — structural BFS then semantic narrative on top candidates
  - `trace(from, to)` — shortest path + per-hop semantic gloss
  - `onboard(area)` — community detection + domain knowledge per cluster

---

## Quick start

### 1. Build the knowledge base for a project

```bash
cd /path/to/your/project
uvx --from askme-mcp askme update .
```

This produces `askme-out/` with:

```
askme-out/
├── graph.json              # Graphify structural graph
├── knowledge-graph.json    # Understand-Anything semantic graph
└── meta.json               # per-file hashes, versions, last-build timestamps
```

The first run rebuilds everything. Subsequent runs are **incremental** — only files whose content hash changed since the last build are re-analyzed. Token cost scales with diff size, not repo size.

### 2. Wire `askme` into your MCP host

Pick the installer for your host (see [Host setup](#host-setup) below):

```bash
# Claude Code (project-scope .mcp.json)
uvx --from askme-mcp askme install claude

# Codex CLI
uvx --from askme-mcp askme install codex

# Gemini CLI
uvx --from askme-mcp askme install gemini
```

Each installer writes a single `askme` MCP server entry pointing at `askme-out/` in the current project, with a timestamped backup of any existing config and a post-install MCP smoke test.

### 3. Use it from your agent

Any MCP-compatible host can now call:

```
askme.ask("how does login retry work?")
askme.trace("LoginViewModel", "AuthRepository")
askme.query_graph("ExoPlayer initialisation")
askme.semantic_explain("aural/player/data/.../PlayerManager.kt")
```

---

## Incremental updates

`askme update` is a single command. There is no `--structural` / `--semantic` split — `askme` figures out what changed and only regenerates the missing slice:

```
askme update .
├── 1. Run Graphify → new graph.json
├── 2. Diff per-file content hashes against meta.json
│      → dirty = added | modified
│      → preserved = unchanged
│      → removed = deleted from repo
├── 3. Carry over semantic entries for preserved files
├── 4. Invoke Understand-Anything ONLY on dirty set
├── 5. Drop semantic entries for removed files
└── 6. Write knowledge-graph.json + meta.json (with new hashes, timestamps, versions)
```

Flags:

- `askme update .` — incremental (default)
- `askme update . --force` — full rebuild, ignore meta.json
- `askme update . --dry-run` — print planned work, no writes
- `askme update . --structural-only` — Graphify only, skip semantic (rare, e.g. for cheap sanity)

---

## Host setup

`askme` follows the MCP spec strictly (JSON-RPC 2.0 over stdio, standard tool schemas). It works in any host that speaks MCP.

### Claude Code

Project-scope `.mcp.json` at your repo root:

```json
{
  "mcpServers": {
    "askme": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "askme-mcp", "--with", "mcp", "askme", "serve", "askme-out/"]
    }
  }
}
```

Or run `uvx --from askme-mcp askme install claude` to write this for you.

### Codex CLI

Writes to `$CODEX_HOME/config.toml` (default `~/.codex/config.toml`):

```toml
[mcp_servers.askme]
args = ["--from", "askme-mcp", "--with", "mcp", "askme", "serve", "/absolute/path/to/askme-out"]
command = "uvx"
startup_timeout_sec = 120
```

Run `uvx --from askme-mcp askme install codex` to write this for you.

### Gemini CLI

Writes `mcpServers` block into `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "askme": {
      "command": "uvx",
      "args": ["--from", "askme-mcp", "--with", "mcp", "askme", "serve", "/absolute/path/to/askme-out"]
    }
  }
}
```

Run `uvx --from askme-mcp askme install gemini` to write this for you.

### AGY

> Status: **not yet supported.** Config path / format for AGY hosts is not documented here. Open an issue if you need it — installer template is one file (`scripts/install-agy.py`) once the path is confirmed.

### Other MCP hosts

`askme serve <askme-out-dir>` speaks stdio MCP. Wire it the same way as any stdio MCP server in your host of choice.

---

## Tool catalogue

| Tool | Source | Description |
|---|---|---|
| `query_graph` | structural | BFS/DFS keyword search over the code graph |
| `get_node` | structural | Look up a single node by label/ID |
| `get_neighbors` | structural | First-hop neighbors of a node |
| `get_community` | structural | Members of a Louvain community |
| `god_nodes` | structural | Highest-centrality nodes (hot spots) |
| `graph_stats` | structural | Graph counts, density, top communities |
| `shortest_path` | structural | Path between two nodes |
| `semantic_explain` | semantic | Narrative explanation of a file or symbol |
| `semantic_chat` | semantic | Free-form question against the knowledge graph |
| `semantic_diff` | semantic | Explain what a git diff changes and why |
| `semantic_onboard` | semantic | Onboarding guide for a module |
| `semantic_domain` | semantic | Business-domain mapping for an area |
| `ask` | hybrid | Structural candidates + semantic narrative in one call |
| `trace` | hybrid | Shortest path with semantic gloss per hop |
| `onboard` | hybrid | Community clusters + domain knowledge per cluster |

All tools return structured JSON. None of them call an LLM internally — they return context bundles for the calling agent's LLM to reason over. This mirrors Graphify's `token_budget` discipline and keeps the MCP host-agnostic.

---

## Architecture

```
askme-mcp (Python, stdio MCP)
├── backends/
│   ├── graphify.py        # imports graphifyy as a library (no subprocess)
│   └── understand.py      # spawns Node subprocess against @understand-anything/core
├── tools/
│   ├── structural.py      # pass-through wrappers around graphify
│   ├── semantic.py        # wrappers around understand skill builders
│   └── hybrid.py          # ask / trace / onboard
├── update.py              # incremental orchestrator
├── diff.py                # per-file hash delta
├── meta.py                # meta.json IO
└── serve.py               # MCP stdio entry point
```

Design rules:

1. **Don't fork upstreams.** Graphify and Understand-Anything are pinned dependencies, never patched.
2. **Schemas stay separate.** Cross-reference by `(file_path, line)` — the only stable join key between the two graphs.
3. **stdout is sacred.** All logs to stderr. stdout is reserved for JSON-RPC frames.
4. **No host detection.** Server behaves identically regardless of caller. No Claude-isms.
5. **No auto-rebuild.** Host decides when to refresh — no file watchers, no background work.

---

## Status

| Capability | State |
|---|---|
| Repo scaffold + MCP stdio entry | ✅ |
| Graphify pass-through tools | 🚧 wiring in progress |
| Incremental `askme update` | 🚧 wiring in progress |
| Semantic tools (Understand-Anything subprocess) | 🚧 stubs |
| Hybrid `ask` / `trace` / `onboard` | 🚧 stubs |
| Claude / Codex / Gemini installers | 🚧 in progress |
| AGY installer | ⏳ blocked on config-path docs |

This is an alpha MVP. APIs may change.

---

## Development

```bash
git clone https://github.com/sughosh-pocketfm/ask-me.git
cd ask-me
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

---

## License

MIT — see [LICENSE](LICENSE).

Built on top of [graphifyy](https://pypi.org/project/graphifyy/) and [@understand-anything/core](https://github.com/Lum1104/Understand-Anything). Their licenses apply to their respective components.
