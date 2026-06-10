# kbask

Hybrid MCP server that combines **[Graphify](https://github.com/graphifyy)** (structural code graphs) with **[Understand-Anything](https://github.com/Lum1104/Understand-Anything)** (LLM-derived semantic knowledge bases) into a single MCP endpoint.

Graphify tells you **where** things are. Understand-Anything tells you **why** they exist. `kbask` joins both and exposes them as MCP tools usable from Claude Code, Codex, Gemini CLI, and any other MCP-compatible host.

---

## Why a hybrid?

| Backend | Strength | Weakness |
|---|---|---|
| Graphify | Exact, cheap, deterministic AST graph (calls, imports, ownership) | No semantics — doesn't know *why* code exists |
| Understand-Anything | Semantic narrative, domain knowledge, onboarding context | Expensive to build, fuzzy, no edge-precise lookups |

`kbask` gives you:

- **All 7 Graphify tools** (`query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`) pass-through
- **5 semantic tools** from Understand-Anything (`semantic_explain`, `semantic_chat`, `semantic_diff`, `semantic_onboard`, `semantic_domain`)
- **Hybrid tools** that compose both:
  - `ask(question)` — structural BFS then semantic narrative on top candidates
  - `trace(from, to)` — shortest path + per-hop semantic gloss
  - `onboard(area)` — community detection + domain knowledge per cluster

---

## Install

> **Status:** `kbask` is **not yet on PyPI**. Install from a GitHub Release or
> directly from source. Once published, `--from kbask` resolves from PyPI
> without changes.

Two install styles. Pick one:

### A. Persistent CLI (`uv tool install`)

Puts `kbask` on your PATH for repeated use:

```bash
curl -fsSL https://raw.githubusercontent.com/sughosh-pocketfm/kbask/main/tool-install.sh | bash
```

The script:
1. Installs `uv` if missing.
2. Resolves the latest GitHub Release wheel (`KBASK_TAG=v0.1.1` to pin).
3. Falls back to `git+https://github.com/sughosh-pocketfm/kbask` if no release exists yet.
4. Runs `uv tool install` so `kbask` lands in `$HOME/.local/bin`.

After install:
```bash
kbask install claude --repo .
kbask update .
kbask --help
```

Upgrade later:
```bash
uv tool upgrade kbask
# or rerun the curl one-liner
```

### B. One-shot installer for an MCP host

Wires kbask into a single host's MCP config without leaving a persistent `kbask` binary:

```bash
curl -fsSL https://raw.githubusercontent.com/sughosh-pocketfm/kbask/main/install.sh | bash -s claude
# or: bash -s codex   |   bash -s gemini
```

The host config itself uses `uvx --from git+...` so the MCP server runs
without a global install.

### Manual paths

```bash
# uvx direct (no scripts)
uvx --from git+https://github.com/sughosh-pocketfm/kbask kbask install claude --repo .

# After PyPI publish
uv tool install kbask
uvx --from kbask kbask install claude --repo .
```

### What the installer does

1. Creates `<repo>/kbask-out/` if missing.
2. Appends `kbask-out/` to `<repo>/.gitignore`.
3. Writes/upserts the host's MCP server config (timestamped backup of any existing file).
4. Writes a `/kbask` slash command for the host:
   - Claude Code → `<repo>/.claude/commands/kbask.md`
   - Codex CLI → `~/.codex/prompts/kbask.md`
   - Gemini CLI → `~/.gemini/commands/kbask.toml`
   - Pass `--no-slash-command` to skip.
5. Runs an MCP `initialize` + `tools/list` smoke test against the configured server.

After restart, you can invoke the slash command from chat: type `/kbask how does X work?` (or just `/kbask` to see its prompt).

### Pin to a fork or tag

```bash
KBASK_SOURCE=git+https://github.com/your-fork/kbask@v0.2.0 \
  uvx --from $KBASK_SOURCE kbask install claude --repo .
```

---

## Build the knowledge base

After installing, build the input artifacts inside your project repo:

```bash
cd /path/to/your/project

# 1. Structural graph (Graphify)
uvx --from graphifyy graphify update .

# 2. Semantic graph (Understand-Anything) — built by an LLM in your host.
#    In Claude Code, run /understand once and let it populate
#    .understand-anything/knowledge-graph.json.

# 3. Mirror both into kbask-out/
uvx --from git+https://github.com/sughosh-pocketfm/kbask kbask update .
```

Produces `kbask-out/`:

```
kbask-out/
├── graph.json              # Graphify structural graph
├── knowledge-graph.json    # Understand-Anything semantic graph (mirrored)
├── knowledge-graph.meta.json
└── meta.json               # per-file hashes, versions, last-build timestamps
```

First run rebuilds everything. Subsequent `kbask update` runs are **incremental** — only files whose content hash changed are re-analysed. Token cost scales with diff size, not repo size.

---

## Use it from your agent

After restart, any MCP-compatible host can call:

```
kbask.ask("how does login retry work?")
kbask.trace("LoginViewModel", "AuthRepository")
kbask.query_graph("ExoPlayer initialisation")
kbask.semantic_explain("aural/player/data/.../PlayerManager.kt")
```

---

## Incremental updates

`kbask update` is a single command. There is no `--structural` / `--semantic` split — `kbask` figures out what changed and only regenerates the missing slice:

```
kbask update .
├── 1. Run Graphify → new graph.json
├── 2. Diff per-file content hashes against meta.json
│      → dirty = added | modified
│      → preserved = unchanged
│      → removed = deleted from repo
├── 3. Mirror <repo>/.understand-anything/knowledge-graph.json → kbask-out/
├── 4. Carry forward unchanged file entries; mark dirty/removed in meta.json
└── 5. Write meta.json (new hashes, timestamps, versions)
```

> **Note on the semantic graph.** Understand-Anything has no self-running analyzer — its knowledge graph is built by an LLM (Claude Code) following the upstream plugin's prompts and persisted to `<repo>/.understand-anything/knowledge-graph.json`. `kbask update` *mirrors* that file into `kbask-out/`; rebuilding the upstream graph is owned by the LLM (e.g. `/understand-update` in Claude Code). If `<repo>/.understand-anything/` is absent, semantic tools still report a clean "not built" error and structural tools keep working.

Flags:

- `kbask update .` — incremental (default)
- `kbask update . --force` — full rebuild, ignore meta.json
- `kbask update . --dry-run` — print planned work, no writes
- `kbask update . --structural-only` — Graphify only, skip semantic mirror

---

## Host setup

`kbask` follows the MCP spec strictly (JSON-RPC 2.0 over stdio, standard tool schemas). It works in any host that speaks MCP.

### Claude Code

Project-scope `.mcp.json` at your repo root:

```json
{
  "mcpServers": {
    "kbask": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/sughosh-pocketfm/kbask",
        "--with", "mcp",
        "kbask", "serve", "kbask-out/"
      ]
    }
  }
}
```

> After PyPI publish, replace `"git+https://github.com/sughosh-pocketfm/kbask"` with `"kbask"`.

Or run the installer:
```bash
uvx --from git+https://github.com/sughosh-pocketfm/kbask kbask install claude --repo .
```

### Codex CLI

Writes to `$CODEX_HOME/config.toml` (default `~/.codex/config.toml`):

```toml
[mcp_servers.kbask]
args = ["--from", "git+https://github.com/sughosh-pocketfm/kbask", "--with", "mcp", "kbask", "serve", "/absolute/path/to/kbask-out"]
command = "uvx"
startup_timeout_sec = 120
```

```bash
uvx --from git+https://github.com/sughosh-pocketfm/kbask kbask install codex --repo .
```

### Gemini CLI

Writes `mcpServers` block into `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "kbask": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/sughosh-pocketfm/kbask",
        "--with", "mcp",
        "kbask", "serve", "/absolute/path/to/kbask-out"
      ]
    }
  }
}
```

```bash
uvx --from git+https://github.com/sughosh-pocketfm/kbask kbask install gemini --repo .
```

### AGY

> Status: **not yet supported.** Config path / format for AGY hosts is not documented here. Open an issue if you need it — installer template is one file (`scripts/install-agy.py`) once the path is confirmed.

### Other MCP hosts

`kbask serve <kbask-out-dir>` speaks stdio MCP. Wire it the same way as any stdio MCP server in your host of choice.

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

### Token accounting

Every tool response carries a `_meta` block reporting the approximate
token + byte cost of that single call:

```json
{
  "...your tool payload...": "...",
  "_meta": {
    "tool": "query_graph",
    "tokens": {"input": 12, "output": 1843, "total": 1855},
    "bytes":  {"input": 47, "output": 7321},
    "encoder": "heuristic:chars/4"
  }
}
```

By default kbask uses a `len(text) / 4` heuristic (good to ~10%). For
tokenizer-accurate counts install the optional extra:

```bash
uv pip install 'kbask[tokens]'    # or: pip install 'kbask[tokens]'
```

That swaps the encoder to `tiktoken:cl100k_base`. The agent can read
`_meta.tokens.total` per call and self-throttle (e.g. drop `depth` or
`token_budget` if a sweep is going hot).

---

## Architecture

```
kbask (Python, stdio MCP)
├── backends/
│   ├── graphify.py        # reuses graphify.serve internals via networkx (no subprocess)
│   └── understand.py      # reads <repo>/.understand-anything/knowledge-graph.json
├── tools/
│   ├── structural.py      # 7 pass-through wrappers around graphify
│   ├── semantic.py        # 5 wrappers reading the mirrored knowledge graph
│   └── hybrid.py          # ask / trace / onboard — compose both backends
├── installers/            # per-host config writers (Claude / Codex / Gemini / AGY)
├── update.py              # incremental orchestrator (hash diff + mirror)
├── diff.py                # per-file hash delta
├── meta.py                # meta.json IO + hash_file
├── state.py               # process-wide out_dir holder
└── serve.py               # MCP stdio entry point — registers 15 tools
```

Design rules:

1. **Don't fork upstreams.** Graphify and Understand-Anything are pinned dependencies, never patched.
2. **Schemas stay separate.** Cross-reference by `(file_path, line)` — the only stable join key between the two graphs.
3. **stdout is sacred.** All logs to stderr. stdout is reserved for JSON-RPC frames.
4. **No host detection.** Server behaves identically regardless of caller. No Claude-isms.
5. **No auto-rebuild.** Host decides when to refresh — no file watchers, no background work.

---

## Releases

Cutting a release:

```bash
# 1. Bump pyproject.toml `version` and src/kbask/__init__.py `__version__` (keep them in sync).
# 2. Commit and tag:
git commit -am "Release v0.1.1"
git tag v0.1.1
git push origin main --tags
```

The `release` GitHub Action (`.github/workflows/release.yml`) fires on the tag:
- Builds wheel + sdist via `uv build`.
- Smoke-tests the wheel (`kbask --help`).
- Generates `SHA256SUMS`.
- Creates a GitHub Release with `*.whl`, `*.tar.gz`, `SHA256SUMS`, `install.sh`, and `tool-install.sh` attached.
- Publishes to PyPI if the `PYPI_TOKEN` repo secret is set.

`tool-install.sh` (curl path) auto-discovers the latest release and prefers the wheel asset over the git source.

---

## Status

| Capability | State |
|---|---|
| Repo scaffold + MCP stdio entry | ✅ |
| Graphify pass-through tools | 🚧 wiring in progress |
| Incremental `kbask update` | ✅ implemented (structural rebuild + semantic mirror) |
| Structural MCP tools (Graphify) | ✅ wired via `graphify.serve` internals |
| Semantic MCP tools (Understand-Anything) | ✅ read knowledge-graph.json directly |
| Hybrid `ask` / `trace` / `onboard` | ✅ compose structural + semantic |
| Hybrid `ask` / `trace` / `onboard` | 🚧 stubs |
| Claude / Codex / Gemini installers | 🚧 in progress |
| AGY installer | ⏳ blocked on config-path docs |

This is an alpha MVP. APIs may change.

---

## Development

```bash
git clone https://github.com/sughosh-pocketfm/kbask.git
cd kbask
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

---

## License

MIT — see [LICENSE](LICENSE).

Built on top of [graphifyy](https://pypi.org/project/graphifyy/) and [@understand-anything/core](https://github.com/Lum1104/Understand-Anything). Their licenses apply to their respective components.
