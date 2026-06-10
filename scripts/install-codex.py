#!/usr/bin/env python3
"""Install askme MCP server into Codex CLI's config.toml."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _installer_common import SERVER_NAME, backup, resolve_out_dir, resolve_uvx, server_args, smoke_test


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _toml_array(values) -> str:
    return "[" + ", ".join(_toml_string(v) for v in values) + "]"


def _render_section(name: str, command: str, args, timeout: int) -> str:
    return "\n".join(
        [
            f"[mcp_servers.{name}]",
            f"args = {_toml_array(args)}",
            f"command = {_toml_string(command)}",
            f"startup_timeout_sec = {timeout}",
            "",
        ]
    )


def _upsert(config_text: str, name: str, section: str) -> str:
    header = f"[mcp_servers.{name}]"
    pattern = re.compile(rf"(?ms)^{re.escape(header)}\n.*?(?=^\[|\Z)")
    if pattern.search(config_text):
        return pattern.sub(section, config_text)
    return config_text.rstrip() + "\n\n" + section


def main() -> int:
    parser = argparse.ArgumentParser(description="Install askme MCP server into Codex config.toml.")
    parser.add_argument("--repo", default=".", help="Repo root containing askme-out/.")
    parser.add_argument(
        "--codex-home",
        default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
        help="Codex home dir. Defaults to $CODEX_HOME or ~/.codex.",
    )
    parser.add_argument("--startup-timeout-sec", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-smoke-test", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    out_dir = resolve_out_dir(repo)
    codex_home = Path(args.codex_home).expanduser().resolve()
    config_path = codex_home / "config.toml"

    uvx = resolve_uvx()
    section = _render_section(SERVER_NAME, uvx, server_args(out_dir), args.startup_timeout_sec)

    if args.dry_run:
        print(section, end="")
        return 0

    codex_home.mkdir(parents=True, exist_ok=True)
    current = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    new_text = _upsert(current, SERVER_NAME, section)
    if new_text != current:
        if config_path.exists():
            print(f"backup: {backup(config_path)}")
        config_path.write_text(new_text, encoding="utf-8")
        print(f"installed '{SERVER_NAME}' in {config_path}")
    else:
        print(f"no change: {config_path}")

    if not args.skip_smoke_test:
        smoke_test(uvx, server_args(out_dir))
    print("restart Codex or reload MCP servers for the change to take effect")
    return 0


if __name__ == "__main__":
    sys.exit(main())
