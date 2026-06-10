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


SERVER_NAME = "askme"
EXPECTED_TOOLS = {
    "query_graph", "get_node", "get_neighbors", "get_community",
    "god_nodes", "graph_stats", "shortest_path",
    "semantic_explain", "semantic_chat", "semantic_diff",
    "semantic_onboard", "semantic_domain",
    "ask", "trace", "onboard",
}


def resolve_uvx() -> str:
    uvx = shutil.which("uvx")
    if uvx is None:
        raise SystemExit(
            "uvx not found on PATH. Install uv first: https://docs.astral.sh/uv/"
        )
    return uvx


def resolve_out_dir(repo: Path) -> Path:
    out = (repo / "askme-out").resolve()
    if not out.exists():
        out.mkdir(parents=True, exist_ok=True)
        print(f"created {out}")
        print("populate it with:  uvx --from askme-mcp askme update .")
    ensure_gitignore(repo, "askme-out/")
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


def server_args(out_dir: Path) -> List[str]:
    return ["--from", "askme-mcp", "--with", "mcp", "askme", "serve", str(out_dir)]


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
                    "clientInfo": {"name": "askme-installer", "version": "0"},
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
