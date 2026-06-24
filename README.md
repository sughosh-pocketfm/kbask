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
- **`reload(target?)`** — drop in-process caches so the next call re-reads `kbask-out/` from disk (`target=all|structural|semantic`, default `all`)

If Understand-Anything is not built for the target repo, hybrid tools automatically degrade to a **graphify-only** mode. The response includes `mode: "graphify-only"`, the structural bundle, file-candidate hints, and a `prompt_hint` that reframes the request (e.g. _"with graphify mcp how does auth work?"_) so the calling LLM reasons from structural data + direct file reads instead of erroring on missing semantic context.

---

## Install

> **Latest release:** [`0.1.2`](https://github.com/sughosh-pocketfm/kbask/releases/tag/0.1.2) — assets: `kbask-0.1.2-py3-none-any.whl`, `kbask-0.1.2.tar.gz`, `SHA256SUMS`, `install.sh`, `tool-install.sh`.
>
> **What's new in 0.1.2:** Hybrid tools (`ask`/`trace`/`onboard`) now auto-fall-back to a **graphify-only** mode when Understand-Anything is not built for the target repo — the response carries a `prompt_hint` that instructs the calling LLM to reason from structural data + direct file reads instead of erroring on missing semantic context.
>
> Not yet on PyPI. Install from the GitHub Release, from `main`, or pinned
> to a tag. Once on PyPI, `--from kbask` resolves from there with no other
> change.

Releases are cut as `X.Y.Z` git tags (the leading `v` is optional — both `0.1.1` and `v0.1.1` are accepted). The `release` GitHub Action
builds a wheel + sdist, attaches them (and `install.sh` / `tool-install.sh` /
`SHA256SUMS`) to the GitHub Release, and — if `PYPI_TOKEN` is configured —
uploads the wheel to PyPI. See **[Releases](#releases)** for the cut process.

Pick the install style that matches your workflow:

### A. Persistent CLI (`uv tool install`) — recommended

Puts `kbask` on your PATH so you can type it like any other tool:

```bash
# Latest release (auto-discovers GitHub Release wheel)
curl -fsSL https://raw.githubusercontent.com/sughosh-pocketfm/kbask/main/tool-install.sh | bash

# Pin to a specific release tag
KBASK_TAG=0.1.1 \
  curl -fsSL https://raw.githubusercontent.com/sughosh-pocketfm/kbask/main/tool-install.sh | bash
```

The script:
1. Installs `uv` if missing (Astral installer).
2. Hits `https://api.github.com/repos/sughosh-pocketfm/kbask/releases/latest`
   to find the wheel asset. Pin a release with `KBASK_TAG=X.Y.Z` (e.g. `KBASK_TAG=0.1.1`).
3. Falls back to `git+https://github.com/sughosh-pocketfm/kbask` if no
   release exists yet (or for `main`).
4. Runs `uv tool install --force` so `kbask` lands in `~/.local/bin`.

After install:
```bash
kbask install claude --repo .     # wire MCP into Claude Code
kbask update .                    # build/refresh knowledge graph
kbask doctor                      # check dependencies
kbask --help
```

See [Upgrade kbask](#upgrade-kbask) for refresh commands.

After upgrading, restart your MCP host (Claude Code / Codex / Gemini) so it respawns `kbask serve` against the new binary.

### B. One-shot host installer (no persistent CLI)

Wires kbask into a single MCP host's config without leaving a global
`kbask` binary. The MCP server itself is spawned by the host via
`uvx --from git+...` on demand.

```bash
curl -fsSL https://raw.githubusercontent.com/sughosh-pocketfm/kbask/main/install.sh | bash -s claude
# or: bash -s codex   |   bash -s gemini

# Pin to a tag (the MCP config gets the same pin):
KBASK_SOURCE="git+https://github.com/sughosh-pocketfm/kbask@0.1.1" \
  curl -fsSL https://raw.githubusercontent.com/sughosh-pocketfm/kbask/main/install.sh | bash -s claude
```

### C. Direct uvx (no scripts)

```bash
# Latest main
uvx --from git+https://github.com/sughosh-pocketfm/kbask kbask install claude --repo .

# Pinned tag
uvx --from "git+https://github.com/sughosh-pocketfm/kbask@0.1.1" kbask install claude --repo .

# From a downloaded wheel (verify SHA256SUMS first)
uvx --from ./kbask-0.1.1-py3-none-any.whl kbask install claude --repo .
```

### D. After PyPI publish

Everything above keeps working, plus:
```bash
uv tool install kbask                  # persistent CLI
uvx --from kbask kbask install claude  # one-shot
uvx kbask --help                       # script + pkg share name
```

### Upgrade kbask

Match the path you installed with:

**A. Persistent CLI (`uv tool install`)**
```bash
# In-place refresh from the latest GitHub Release (verifies SHA256SUMS):
kbask update-bin
# Pin a specific tag:
kbask update-bin --tag 0.1.1
# Or use uv directly:
uv tool upgrade kbask
# Or rerun the curl one-liner (always uses --force):
curl -fsSL https://raw.githubusercontent.com/sughosh-pocketfm/kbask/main/tool-install.sh | bash
KBASK_TAG=0.1.1 curl -fsSL https://raw.githubusercontent.com/sughosh-pocketfm/kbask/main/tool-install.sh | bash
```

**B/C. `uvx` ephemeral (hosts spawn it on demand)**

`uvx --from kbask kbask serve` (or the git/wheel form) refetches per spawn. To force a fresh pull instead of the cached version:
```bash
uv cache clean kbask
```

**Local wheel**
```bash
uv tool install --force ./kbask-0.1.1-py3-none-any.whl
```

After upgrading, **restart your MCP host** (Claude Code / Codex / Gemini) so it respawns `kbask serve` against the new binary. Existing host sessions keep the old process until restart.

### Verify a release artifact

```bash
# From the release page, grab SHA256SUMS + the wheel
shasum -a 256 -c SHA256SUMS
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

### Dependency preflight

Both `kbask install <host>` and `kbask update` print a status report for the upstreams kbask depends on:

```
[ok]   graphifyy ........... 0.5.0 (importable)
[ok]   graphify CLI ........ runnable (graphify or uvx on PATH)
[warn] understand-anything . knowledge graph not built yet
       To build:
         1. /plugin marketplace add Lum1104/Understand-Anything
         2. /plugin install understand-anything    (inside Claude Code)
         3. /understand                             (from this repo, in Claude Code)
         4. kbask update .
```

Run it standalone any time:

```bash
kbask doctor [path/to/repo]
```

- `graphifyy` is a hard dep — installed transitively with kbask.
- `understand-anything` is built by an LLM in Claude Code (no analyzer binary). Even Codex / Gemini users build the graph via Claude Code once, then kbask mirrors it.

### Pin to a fork

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
| `reload` | admin | Drop in-process caches; next call re-reads `kbask-out/` from disk (`target=all\|structural\|semantic`) |

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
└── serve.py               # MCP stdio entry point — registers 16 tools
```

Design rules:

1. **Don't fork upstreams.** Graphify and Understand-Anything are pinned dependencies, never patched.
2. **Schemas stay separate.** Cross-reference by `(file_path, line)` — the only stable join key between the two graphs.
3. **stdout is sacred.** All logs to stderr. stdout is reserved for JSON-RPC frames.
4. **No host detection.** Server behaves identically regardless of caller. No Claude-isms.
5. **No auto-rebuild.** Host decides when to refresh — no file watchers, no background work.

---

## Releases

### Versioning

`v<MAJOR>.<MINOR>.<PATCH>` (SemVer). Pre-1.0 — breaking changes can land on any minor bump.

The release tag is the source of truth. The release workflow strips an optional
leading `v`, writes that version into `pyproject.toml` and
`src/kbask/__init__.py` before building, and then commits the same version bump
back to `main` if needed.

### Cutting a release

```bash
# Tag the commit you want to release; both styles are accepted.
git tag 0.1.1
git push origin main --tags
```

Manual run (e.g. to re-cut from a fixed branch) is also supported:

```bash
gh workflow run release.yml -f tag=0.1.1
```

### What the release pipeline does

`.github/workflows/release.yml` on tag push:

1. Checks out at the tag.
2. Sets up `uv` and Python 3.11.
3. Resolves the version from the tag and writes it into source files.
4. `uv build` → `dist/kbask-X.Y.Z-py3-none-any.whl` and `dist/kbask-X.Y.Z.tar.gz`.
5. Smoke-tests the wheel — `pip install` + `kbask --help` must succeed.
6. Generates `SHA256SUMS`.
7. Creates the GitHub Release with auto-generated changelog and the following assets attached:
   - `kbask-X.Y.Z-py3-none-any.whl`
   - `kbask-X.Y.Z.tar.gz`
   - `SHA256SUMS`
   - `install.sh`           (one-shot host installer bootstrap)
   - `tool-install.sh`      (`uv tool install` bootstrap)
8. Publishes to PyPI **only if** the `PYPI_TOKEN` repo secret is configured.
9. Commits `chore(release): bump version to X.Y.Z [skip ci]` back to `main`
   when `main` does not already contain that version.

### Required repo secrets

| Secret | Purpose | Optional? |
|---|---|---|
| `PYPI_TOKEN` | `uv publish` API token | Yes — release runs without it; only PyPI step is skipped. |

`GITHUB_TOKEN` is provided automatically (used by `softprops/action-gh-release` for the Release write).

### Consumer install paths after release

Once the release exists:

```bash
# A. Persistent CLI — auto-finds the wheel
curl -fsSL https://raw.githubusercontent.com/sughosh-pocketfm/kbask/main/tool-install.sh | bash

# B. Pinned tag
KBASK_TAG=0.1.1 curl -fsSL https://raw.githubusercontent.com/sughosh-pocketfm/kbask/main/tool-install.sh | bash

# C. Direct download
gh release download 0.1.1 --repo sughosh-pocketfm/kbask --pattern '*.whl'
shasum -a 256 -c SHA256SUMS
uv tool install ./kbask-0.1.1-py3-none-any.whl
```

`tool-install.sh` hits `GET /repos/{owner}/{repo}/releases/latest` to discover the newest tag and prefers the wheel asset over the git source.

---

## Status

| Capability | State |
|---|---|
| MCP stdio server + 16 tools | ✅ |
| Structural tools via `graphify.serve` internals | ✅ |
| Semantic tools reading mirrored knowledge graph | ✅ |
| Hybrid `ask` / `trace` / `onboard` (3-stage cascade) | ✅ |
| Incremental `kbask update` | ✅ structural rebuild + semantic mirror |
| Per-tool `_meta.tokens` accounting | ✅ heuristic; `kbask[tokens]` extra for tiktoken |
| Tolerant node lookup (path / basename / label / id) | ✅ |
| Dependency preflight (`kbask doctor`) | ✅ |
| `/kbask` slash command writer (Claude/Codex/Gemini) | ✅ |
| Installer scripts (Claude/Codex/Gemini) | ✅ |
| `tool-install.sh` + `install.sh` curl bootstraps | ✅ |
| GitHub Release pipeline (wheel/sdist/checksums) | ✅ |
| PyPI publish | ⏳ token not yet configured |
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
