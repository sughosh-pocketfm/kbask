"""Shared helpers for per-host MCP installer scripts."""

from __future__ import annotations

import json
import os
import re
import selectors
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


SERVER_NAME = "kbask"
REPO_SLUG = "sughosh-pocketfm/kbask"

# `uvx --from <SOURCE>` value. Until PyPI publish, default to the git repo so
# `uvx` fetches kbask-mcp straight from GitHub. Override with $KBASK_SOURCE or
# --source.
DEFAULT_SOURCE = "kbask"

EXPECTED_TOOLS = {
    "query_graph", "get_node", "get_neighbors", "get_community",
    "god_nodes", "graph_stats", "shortest_path",
    "semantic_explain", "semantic_chat", "semantic_diff",
    "semantic_onboard", "semantic_domain",
    "ask", "trace", "onboard",
    "reload",
}


def resolve_uvx() -> str:
    uvx = shutil.which("uvx")
    if uvx is None:
        raise SystemExit(
            "uvx not found on PATH. Install uv first: https://docs.astral.sh/uv/"
        )
    return uvx


def resolve_out_dir(repo: Path) -> Path:
    out = (repo / "kbask-out").resolve()
    if not out.exists():
        out.mkdir(parents=True, exist_ok=True)
        print(f"created {out}")
        print(f"populate it with:  uvx --from {DEFAULT_SOURCE} kbask update .")
    ensure_gitignore(repo, "kbask-out/")
    return out


def ensure_gitignore(repo: Path, pattern: str) -> None:
    """Append `pattern` to <repo>/.gitignore if not already present."""
    gi = repo / ".gitignore"
    if gi.exists():
        lines = gi.read_text(encoding="utf-8").splitlines()
        existing = {ln.strip() for ln in lines}
        if pattern in existing or pattern.rstrip("/") in existing:
            return
        prefix = "" if not lines or lines[-1] == "" else "\n"
        with gi.open("a", encoding="utf-8") as fh:
            fh.write(f"{prefix}{pattern}\n")
        print(f"added '{pattern}' to {gi}")
    else:
        gi.write_text(f"{pattern}\n", encoding="utf-8")
        print(f"created {gi} with '{pattern}'")


def resolve_source(explicit: str | None = None) -> str:
    return explicit or os.environ.get("KBASK_SOURCE") or DEFAULT_SOURCE


def server_args(out_dir: Path, source: str | None = None) -> List[str]:
    return [
        "--from", resolve_source(source),
        "--with", "mcp",
        "kbask", "serve", str(out_dir),
    ]


PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "kbask.md"


# ------------------------------------------------------------------
# Dependency pre-flight
# ------------------------------------------------------------------

def check_dependencies(repo: Path) -> Dict[str, Dict[str, object]]:
    """Probe upstreams kbask depends on. Print a status line per check.

    Returns a status dict but the main effect is the printed report:

      [ok]   graphifyy ........... 0.5.0 (importable)
      [warn] understand-anything . knowledge graph missing — run /understand in Claude Code

    Nothing here aborts. Callers decide whether to continue. The goal
    is to make missing prerequisites obvious *before* the MCP server
    silently degrades.
    """
    status: Dict[str, Dict[str, object]] = {}

    # graphifyy: hard runtime dep, already in pyproject. Verify importability.
    try:
        import graphify  # type: ignore[import-not-found]
        gv = getattr(graphify, "__version__", "unknown")
        status["graphifyy"] = {"ok": True, "version": gv, "note": "importable"}
        print(f"[ok]   graphifyy ........... {gv} (importable)")
    except ImportError as exc:
        status["graphifyy"] = {"ok": False, "error": str(exc)}
        print(
            "[err]  graphifyy ........... MISSING\n"
            "       Should have come in via kbask deps. Reinstall:\n"
            f"         uv tool install --reinstall git+https://github.com/{REPO_SLUG}\n"
            "       or:\n"
            f"         uvx --refresh --from git+https://github.com/{REPO_SLUG} kbask --help"
        )

    # graphify CLI: required for `kbask update` to build the structural graph.
    if shutil.which("graphify") or shutil.which("uvx"):
        status["graphify-cli"] = {"ok": True, "note": "graphify or uvx on PATH"}
        print("[ok]   graphify CLI ........ runnable (graphify or uvx on PATH)")
    else:
        status["graphify-cli"] = {"ok": False}
        print(
            "[warn] graphify CLI ........ neither `graphify` nor `uvx` on PATH\n"
            "       Install uv: https://docs.astral.sh/uv/"
        )

    # understand-anything: LLM-built plugin output; can't be auto-installed.
    ua_dir = repo / ".understand-anything"
    ua_graph = ua_dir / "knowledge-graph.json"
    if ua_graph.exists():
        try:
            size_kb = ua_graph.stat().st_size // 1024
        except OSError:
            size_kb = 0
        status["understand-anything"] = {"ok": True, "size_kb": size_kb}
        print(f"[ok]   understand-anything . {ua_graph} ({size_kb} KB)")
    else:
        status["understand-anything"] = {"ok": False}
        print(
            "[warn] understand-anything . knowledge graph not built yet\n"
            "       Semantic tools will return clean 'not built' errors until built.\n"
            "       To build:\n"
            "         1. Install the Understand-Anything plugin in Claude Code:\n"
            "            /plugin marketplace add Lum1104/Understand-Anything\n"
            "            /plugin install understand-anything\n"
            "         2. From inside this repo, run: /understand\n"
            "         3. Then: kbask update ."
        )

    return status


def _read_prompt() -> Tuple[str, str]:
    """Return (description, body) parsed from the bundled kbask.md prompt."""
    raw = PROMPT_PATH.read_text(encoding="utf-8")
    description = "Query the kbask MCP server for code knowledge."
    body = raw
    if raw.startswith("---\n"):
        end = raw.find("\n---\n", 4)
        if end != -1:
            front = raw[4:end]
            body = raw[end + 5 :].lstrip("\n")
            for ln in front.splitlines():
                if ln.startswith("description:"):
                    description = ln.split(":", 1)[1].strip()
                    break
    return description, body


def install_slash_command(dest: Path, fmt: str = "markdown") -> None:
    """Write the /kbask slash command at `dest`.

    fmt:
      - "markdown": Claude Code / Codex CLI flavor (frontmatter + body).
      - "toml":     Gemini CLI flavor (`description` + `prompt`).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    description, body = _read_prompt()

    if fmt == "markdown":
        content = PROMPT_PATH.read_text(encoding="utf-8")
    elif fmt == "toml":
        prompt_literal = body.replace('"""', '\\"\\"\\"')
        content = (
            f"description = {json.dumps(description)}\n"
            f'prompt = """\n{prompt_literal}"""\n'
        )
    else:
        raise ValueError(f"unknown slash-command format: {fmt!r}")

    if dest.exists():
        if dest.read_text(encoding="utf-8") == content:
            print(f"slash command up to date: {dest}")
            return
        print(f"backup: {backup(dest)}")
    dest.write_text(content, encoding="utf-8")
    print(f"wrote slash command: {dest}")


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def smoke_test(command: str, args: List[str], timeout_sec: int = 20) -> None:
    """Run a minimal MCP initialize + tools/list handshake against the configured server."""
    proc = subprocess.Popen(
        [command, *args],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    try:
        messages = [
            {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "kbask-installer", "version": "0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        assert proc.stdin is not None
        for msg in messages:
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()

        assert proc.stdout is not None and proc.stderr is not None
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
        selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
        responses: Dict[int, dict] = {}
        stderr_lines: List[str] = []
        deadline = time.time() + timeout_sec
        while time.time() < deadline and 2 not in responses:
            for key, _ in selector.select(timeout=0.5):
                line = key.fileobj.readline()
                if not line:
                    continue
                if key.data == "stderr":
                    stderr_lines.append(line.strip())
                    continue
                payload = json.loads(line)
                if "id" in payload:
                    responses[payload["id"]] = payload

        if 1 not in responses or 2 not in responses:
            detail = "\n".join(stderr_lines[-10:])
            raise SystemExit(f"MCP smoke test timed out.\n{detail}")

        tools = {tool["name"] for tool in responses[2]["result"]["tools"]}
        missing = sorted(EXPECTED_TOOLS - tools)
        if missing:
            raise SystemExit(f"smoke test missing tools: {', '.join(missing)}")
        print("smoke test: ok")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
