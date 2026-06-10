#!/usr/bin/env python3
"""Install askme MCP server into a project-scope .mcp.json for Claude Code."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _installer_common import SERVER_NAME, backup, resolve_out_dir, resolve_uvx, server_args, smoke_test


def main() -> int:
    parser = argparse.ArgumentParser(description="Install askme MCP server into Claude Code .mcp.json.")
    parser.add_argument("--repo", default=".", help="Repo root containing askme-out/.")
    parser.add_argument("--config", help="Override .mcp.json path. Defaults to <repo>/.mcp.json.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-smoke-test", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    out_dir = resolve_out_dir(repo)
    config_path = Path(args.config).expanduser().resolve() if args.config else repo / ".mcp.json"

    uvx = resolve_uvx()
    entry = {
        "type": "stdio",
        "command": uvx,
        "args": server_args(out_dir),
    }

    if args.dry_run:
        print(json.dumps({SERVER_NAME: entry}, indent=2))
        return 0

    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        backup_path = backup(config_path)
        print(f"backup: {backup_path}")
    else:
        data = {}

    data.setdefault("mcpServers", {})[SERVER_NAME] = entry
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"installed '{SERVER_NAME}' in {config_path}")

    if not args.skip_smoke_test:
        smoke_test(uvx, server_args(out_dir))
    print("restart Claude Code to load the new MCP server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
