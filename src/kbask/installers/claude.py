"""Install kbask MCP server into Claude Code project-scope .mcp.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kbask.installers.common import (
    SERVER_NAME,
    backup,
    install_slash_command,
    resolve_out_dir,
    resolve_uvx,
    server_args,
    smoke_test,
)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".", help="Repo root containing kbask-out/.")
    parser.add_argument("--config", help="Override .mcp.json path. Defaults to <repo>/.mcp.json.")
    parser.add_argument("--source", help="uvx --from value. Defaults to $KBASK_SOURCE or the git repo.")
    parser.add_argument("--no-slash-command", action="store_true",
                        help="Skip writing the /kbask slash command.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-smoke-test", action="store_true")


def main(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser().resolve()
    out_dir = resolve_out_dir(repo)
    config_path = Path(args.config).expanduser().resolve() if args.config else repo / ".mcp.json"

    uvx = resolve_uvx()
    entry = {"type": "stdio", "command": uvx, "args": server_args(out_dir, args.source)}

    if args.dry_run:
        print(json.dumps({SERVER_NAME: entry}, indent=2))
        return 0

    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        print(f"backup: {backup(config_path)}")
    else:
        data = {}

    data.setdefault("mcpServers", {})[SERVER_NAME] = entry
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"installed '{SERVER_NAME}' in {config_path}")

    if not args.no_slash_command:
        install_slash_command(repo / ".claude" / "commands" / "kbask.md", fmt="markdown")

    if not args.skip_smoke_test:
        smoke_test(uvx, server_args(out_dir, args.source))
    print("restart Claude Code to load the new MCP server")
    return 0
