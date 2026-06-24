# CLAUDE.md — kbask

Guidance for Claude Code (and other AI agents) working in this repo.

---

## What this project is

`kbask` is a single Python MCP (Model Context Protocol) server that
joins two upstream code-analysis tools into one MCP endpoint:

- **[Graphify](https://pypi.org/project/graphifyy/)** — deterministic
  tree-sitter AST graph (calls, imports, ownership). Tells you *where*
  things are.
- **[Understand-Anything](https://github.com/Lum1104/Understand-Anything)**
  — LLM-derived semantic knowledge graph (purpose, domain, onboarding
  narrative). Tells you *why* things exist.

The product value is the **hybrid** layer (`ask` / `trace` / `onboard`),
which queries the structural graph and decorates the result with the
semantic graph's narrative. The host LLM (Claude / Codex / Gemini) does
the synthesis — `kbask` itself never calls a model.

Host-agnostic: works in any MCP-compatible client (Claude Code, Codex
CLI, Gemini CLI, AGY future).

Public repo: <https://github.com/sughosh-pocketfm/kbask>.
PyPI name target: `kbask` (fallback `kbask`).

---

## Critical mental model

### Graphify is a self-running CLI; Understand-Anything is not.

- `graphify update .` runs deterministically — tree-sitter parses, writes
  `graphify-out/graph.json`. Cheap, fast, idempotent.
- Understand-Anything has **no analyzer binary**. Its knowledge graph is
  built by an **LLM** following prompts shipped in the Claude Code plugin
  (`auto-update-prompt.md`). The output lives at
  `<repo>/.understand-anything/knowledge-graph.json`.

So `kbask update` does *not* rebuild the semantic graph from scratch. It:

1. Runs `graphify update` for the structural side.
2. **Mirrors** the upstream `.understand-anything/knowledge-graph.json`
   into `kbask-out/knowledge-graph.json` if present.
3. Tracks per-file content hashes in `kbask-out/meta.json` for incremental
   change detection.

If `.understand-anything/` is absent, structural tools still work; the
semantic tools return a clean `not built` error pointing the user at the
right command in their host (`/understand-update` in Claude Code).

**Do not** try to write a "real" understand-anything analyzer here. If
you find yourself spawning Node subprocesses to invoke
`@understand-anything/core`'s graph builder, you are off-path. The
upstream design owns rebuilding; kbask owns serving.

---

## Repo layout

```
kbask/
├── pyproject.toml              # package metadata, deps (mcp, graphifyy)
├── README.md                   # user-facing docs
├── CLAUDE.md                   # ← you are here
├── LICENSE                     # MIT
├── .gitignore                  # ignores kbask-out/, *.pyc, etc
├── src/kbask/
│   ├── __init__.py             # __version__
│   ├── cli.py                  # argparse dispatcher → {serve, update, install, health}
│   ├── serve.py                # MCP stdio server, tool registry
│   ├── update.py               # incremental update orchestrator
│   ├── install.py              # `kbask install <host>` → dispatch to scripts/install-*.py
│   ├── health.py               # `kbask health` reporter
│   ├── state.py                # process-wide out_dir holder (set by serve.run)
│   ├── meta.py                 # meta.json schema + IO + hash_file
│   ├── diff.py                 # per-file delta (added/modified/removed/unchanged)
│   ├── backends/
│   │   ├── graphify.py         # graphify networkx wrapper + 7 tool funcs
│   │   └── understand.py       # knowledge-graph.json reader + 5 tool funcs
│   └── tools/
│       ├── structural.py       # passthrough to backends.graphify
│       ├── semantic.py         # passthrough to backends.understand
│       └── hybrid.py           # ask / trace / onboard — compose both
│   ├── installers/             # ships in wheel — `kbask install <host>` dispatcher
│   │   ├── common.py           # backup/upsert/smoke-test, $KBASK_SOURCE default
│   │   ├── claude.py           # writes <repo>/.mcp.json (project-scope)
│   │   ├── codex.py            # writes ~/.codex/config.toml
│   │   ├── gemini.py           # writes ~/.gemini/settings.json
│   │   └── agy.py              # placeholder, format unknown
├── scripts/
│   └── install-{host}.py       # thin trampolines into kbask.installers.*
└── tests/
    └── test_diff.py            # delta logic tests (added/modified/removed/unchanged)
```

In the **user's** project repo at runtime:

```
<user-repo>/
├── .git/
├── .understand-anything/
│   ├── knowledge-graph.json    # LLM-built upstream — kbask INPUT
│   └── meta.json
├── graphify-out/
│   └── graph.json              # graphify CLI output, kbask INPUT
└── kbask-out/                  # kbask OUTPUT — gitignored
    ├── graph.json              # mirrored from graphify-out/
    ├── knowledge-graph.json    # mirrored from .understand-anything/
    ├── knowledge-graph.meta.json
    └── meta.json               # per-file hashes, versions, git sha
```

---

## How the pieces wire

### Startup
```
host (Claude/Codex/Gemini)
  └─ spawns: uvx --from kbask kbask serve <kbask-out>
       └─ kbask.cli.main()
            └─ kbask.serve.run(out_dir)
                 ├─ state.set_out_dir(out_dir)
                 ├─ register 16 tools in _TOOLS dict
                 └─ mcp.server.stdio.stdio_server → JSON-RPC 2.0 loop
```

### Tool call lifecycle
```
host → JSON-RPC {tools/call, name: "query_graph", args: {...}}
  └─ serve.py: call_tool()
       └─ _TOOLS["query_graph"]["fn"](**args)
            └─ tools.structural.query_graph(...)
                 └─ backends.graphify.query_graph(...)
                      ├─ _load() — lazy load networkx graph (mtime-keyed cache)
                      └─ uses graphify.serve internals (_score_nodes, _bfs, ...)
                 → dict result
       → TextContent(json.dumps(result))
```

### State

`kbask.state` holds ONE thing: the absolute path to `kbask-out/`. It is
set exactly once, by `serve.run`. Every backend reads from it via
`state.graph_path()`, `state.knowledge_graph_path()`, `state.meta_path()`.

Never thread `out_dir` through function args. Never set `state.out_dir`
from anywhere except `serve.run`.

### Caches

- `backends.graphify._graph_cache` — keyed by `(path, mtime_ns)`.
  Invalidates automatically when `graph.json` changes on disk.
- `backends.understand._kg_cache` — same pattern for `knowledge-graph.json`.

Both caches are per-process. The MCP server lives long enough to benefit
from caching; CLI commands (`update`, `health`) typically don't hit them.

---

## Adding a new tool

1. Implement the backend function in `backends/graphify.py` or
   `backends/understand.py` — keep it pure (in → out dict). Use
   `_load()` / `_load_kg()` for graph state.
2. Add a thin passthrough in `tools/structural.py` or `tools/semantic.py`.
3. Register in `serve.py`'s `_TOOLS` dict with a permissive JSONSchema.
4. If hybrid, add to `tools/hybrid.py` and register the same way.

Tool handlers MUST:
- Return a JSON-serializable dict (no Path objects, no custom classes
  unless they're `dataclasses.dataclass`).
- Raise `GraphifyUnavailable` / `UnderstandUnavailable` for backend
  failure — `serve.py` maps these to structured JSON errors.
- Not log to stdout. Use the `logger` (stderr). **stdout is reserved for
  JSON-RPC frames.**

---

## Adding a new host installer

1. Copy `scripts/install-gemini.py` as the closest template (JSON config).
2. Use helpers from `scripts/_installer_common.py`:
   - `validate_server_name(name)` — guard against config injection
   - `backup_with_timestamp(path)` — never overwrite without a `.bak.<ts>`
   - `smoke_test(command, args)` — JSON-RPC `initialize` + `tools/list`
3. Resolve `kbask-out/` to an **absolute path** before writing config —
   relative paths break when hosts spawn from a different cwd.
4. Test against a real installation of the target host.

---

## Coding conventions

- Python **3.10+** (we use `from __future__ import annotations`, PEP 604
  union syntax in annotations).
- Type-hint everything. No `Any` if you can avoid it.
- No comments restating WHAT the code does — names + types do that. Only
  comment WHY when non-obvious (e.g. "graphify CLI writes here regardless
  of flags").
- Errors propagate as typed exceptions (`GraphifyUnavailable`,
  `UnderstandUnavailable`) — never `bare except`, never `return None` for
  failure.
- Subprocess calls: always pass `capture_output=True, text=True`. Never
  shell=True.
- stdout = JSON-RPC frames only. Logging via `logging.basicConfig(stream=sys.stderr, ...)`.

---

## What NOT to do

- ❌ Do **not** import `mcp` at module top-level outside of `serve.py`.
  It's an optional runtime dep — keep imports lazy so `kbask update`
  works without it.
- ❌ Do **not** write to stdout from tool handlers or backends.
- ❌ Do **not** rebuild Understand-Anything's knowledge graph here. See
  "Critical mental model" above.
- ❌ Do **not** add background tasks, file watchers, or auto-rebuild
  hooks in the MCP server. The host owns cadence.
- ❌ Do **not** add host-specific behavior to the MCP server. If a host
  needs a quirk, that lives in its installer script.
- ❌ Do **not** commit `kbask-out/` or any `*.json` produced by tools.
  `.gitignore` already covers it.
- ❌ Do **not** depend on `networkx` or `tree-sitter` directly — both
  arrive transitively through `graphifyy`. Re-pinning them ourselves
  causes version drift.

---

## Common tasks

### Local dev loop
```bash
# from a sibling repo that has a graphify-out/ and .understand-anything/:
PYTHONPATH=$KBASK_CHECKOUT/src \
  python3 -m kbask.cli update .

PYTHONPATH=$KBASK_CHECKOUT/src \
  python3 -m kbask.cli health

# MCP stdio server (rare to test directly; usually via a host):
PYTHONPATH=$KBASK_CHECKOUT/src \
  python3 -m kbask.cli serve kbask-out/
```

### Run tests
```bash
cd $KBASK_CHECKOUT
PYTHONPATH=src python3 -c "
from tests import test_diff
for n in dir(test_diff):
    if n.startswith('test_'):
        getattr(test_diff, n)()
        print('PASS', n)
"
```
(No pytest dep in `[project.optional-dependencies].dev` is enforced yet —
tests are plain `assert`s, runnable directly.)

### Install into a host (against the local checkout)
```bash
python3 scripts/install-claude.py /path/to/target/repo --kbask-out /path/to/kbask-out
python3 scripts/install-codex.py  --kbask-out /path/to/kbask-out
python3 scripts/install-gemini.py --kbask-out /path/to/kbask-out
```

### Cut a release
- Tag the commit to release with `X.Y.Z` or `vX.Y.Z`.
- The release workflow writes that tag version into `pyproject.toml` and
  `src/kbask/__init__.py` before building.
- After publishing, the workflow commits the same version bump back to `main`
  if `main` does not already contain it.

---

## Tool catalogue (current)

| Tool              | Layer       | Calls (under the hood)                                  |
|-------------------|-------------|---------------------------------------------------------|
| `query_graph`     | structural  | `graphify.serve._score_nodes` + `_bfs`/`_dfs`           |
| `get_node`        | structural  | `nx.Graph.nodes(data=True)` label lookup                |
| `get_neighbors`   | structural  | `graphify.serve._find_node` + `nx.Graph.neighbors`      |
| `get_community`   | structural  | Louvain output from `_communities_from_graph`           |
| `god_nodes`       | structural  | `graphify.analyze.god_nodes`                            |
| `graph_stats`     | structural  | `nx.Graph` counts + confidence histogram                |
| `shortest_path`   | structural  | `nx.shortest_path`                                      |
| `semantic_explain`| semantic    | `knowledge-graph.json` entity/file match                |
| `semantic_chat`   | semantic    | scored term match over entity summary/description       |
| `semantic_diff`   | semantic    | `knowledge-graph.json` precomputed `diffs[base..head]`  |
| `semantic_onboard`| semantic    | `knowledge-graph.json` `onboarding[area]` + entities    |
| `semantic_domain` | semantic    | `knowledge-graph.json` `domain` map                     |
| `ask`             | hybrid      | `query_graph` → `semantic_explain` per top-k candidate  |
| `trace`           | hybrid      | `shortest_path` → `semantic_explain` per hop            |
| `onboard`         | hybrid      | `query_graph` + `semantic_onboard` side-by-side         |
| `reload`          | admin       | drops in-process caches; next call re-reads disk         |

---

## Known limitations / TODO

- **AGY installer** is a placeholder — config path/format unknown. Awaiting
  a confirmed AGY config location before shipping.
- **`semantic_diff`** depends on Understand-Anything writing diff entries
  into `knowledge-graph.json`. If the upstream schema doesn't yet expose
  this, the tool will report `no precomputed diff entry`.
- **No unit tests yet** for `backends/graphify.py` or
  `backends/understand.py` — both require fixture graph JSON files. Add
  when first bug hits.
- **Schema versions**: `meta.SCHEMA_VERSION` is 1. When you change
  `meta.json` shape, bump it and add a migration path in `meta.load`.
- **Public API stability**: `graphify.serve._foo` helpers are
  underscore-prefixed in upstream. We rely on them. Pin `graphifyy` in
  `pyproject.toml` and integration-test on every bump.

---

## Origin context

- Built 2026-06-10 as the hybrid successor to two separate MCP plugins
  (graphify + understand-anything) inside the `android_client` repo.
- Original Jira: **DROID-8218** (ask-me MCP / Codex installer track).
- Earlier sibling work: `scripts/install-graphify-codex-mcp.py` in
  `android_client` — that pattern (single-file installer with
  upsert/backup/smoke-test) is the template all `scripts/install-*.py`
  files in this repo follow.
