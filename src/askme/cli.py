"""Top-level CLI dispatcher for askme."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="askme",
        description="Hybrid MCP server combining Graphify + Understand-Anything.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Start the MCP stdio server.")
    p_serve.add_argument(
        "out_dir",
        nargs="?",
        default="askme-out",
        help="Path to the askme-out directory. Defaults to ./askme-out.",
    )

    p_update = sub.add_parser("update", help="Build or refresh askme-out incrementally.")
    p_update.add_argument("repo", nargs="?", default=".", help="Repo root. Defaults to cwd.")
    p_update.add_argument("--force", action="store_true", help="Full rebuild, ignore meta.json.")
    p_update.add_argument("--dry-run", action="store_true", help="Report planned work, no writes.")
    p_update.add_argument(
        "--structural-only",
        action="store_true",
        help="Graphify only, skip semantic rebuild.",
    )

    p_install = sub.add_parser("install", help="Install askme MCP server into a host config.")
    p_install.add_argument(
        "host",
        choices=("claude", "codex", "gemini"),
        help="Target host. AGY is not yet supported.",
    )
    p_install.add_argument("--repo", default=".", help="Repo root used to resolve askme-out/.")
    p_install.add_argument("--dry-run", action="store_true")

    sub.add_parser("health", help="Print backend versions and graph freshness.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "serve":
        from askme.serve import run

        return run(Path(args.out_dir).resolve())

    if args.command == "update":
        from askme.update import run

        return run(
            repo=Path(args.repo).resolve(),
            force=args.force,
            dry_run=args.dry_run,
            structural_only=args.structural_only,
        )

    if args.command == "install":
        from askme.install import run

        return run(host=args.host, repo=Path(args.repo).resolve(), dry_run=args.dry_run)

    if args.command == "health":
        from askme.health import run

        return run()

    return 2


if __name__ == "__main__":
    sys.exit(main())
