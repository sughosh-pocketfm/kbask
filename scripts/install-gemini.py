#!/usr/bin/env python3
"""Install askme MCP server into Gemini CLI's ~/.gemini/settings.json."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _installer_common import SERVER_NAME, backup, resolve_out_dir, resolve_uvx, server_args, smoke_test


def main() -> int:
    parser = argparse.ArgumentParser(description="Install askme MCP server into Gemini CLI settings.")
    parser.add_argument("--repo", default=".", help="Repo root containing askme-out/.")
    parser.add_argument(
        "--gemini-home",
        default=os.environ.get("GEMINI_HOME", str(Path.home() / ".gemini")),
        help="Gemini home dir. Defaults to $GEMINI_HOME or ~/.gemini.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-smoke-test", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    out_dir = resolve_out_dir(repo)
    gemini_home = Path(args.gemini_home).expanduser().resolve()
    config_path = gemini_home / "settings.json"

    uvx = resolve_uvx()
    entry = {
        "command": uvx,
        "args": server_args(out_dir),
    }

    if args.dry_run:
        print(json.dumps({"mcpServers": {SERVER_NAME: entry}}, indent=2))
        return 0

    gemini_home.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        print(f"backup: {backup(config_path)}")
    else:
        data = {}

    data.setdefault("mcpServers", {})[SERVER_NAME] = entry
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"installed '{SERVER_NAME}' in {config_path}")

    if not args.skip_smoke_test:
        smoke_test(uvx, server_args(out_dir))
    print("restart Gemini CLI to load the new MCP server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
