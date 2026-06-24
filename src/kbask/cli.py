"""Top-level CLI dispatcher for kbask."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kbask",
        description="Hybrid MCP server combining Graphify + Understand-Anything.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Start the MCP stdio server.")
    p_serve.add_argument(
        "out_dir",
        nargs="?",
        default="kbask-out",
        help="Path to the kbask-out directory. Defaults to ./kbask-out.",
    )

    p_update = sub.add_parser("update", help="Build or refresh kbask-out incrementally.")
    p_update.add_argument("repo", nargs="?", default=".", help="Repo root. Defaults to cwd.")
    p_update.add_argument("--force", action="store_true", help="Full rebuild, ignore meta.json.")
    p_update.add_argument("--dry-run", action="store_true", help="Report planned work, no writes.")
    p_update.add_argument(
        "--structural-only",
        action="store_true",
        help="Graphify only, skip semantic rebuild.",
    )

    p_install = sub.add_parser(
        "install",
        help="Install kbask MCP server into a host config.",
    )
    p_install.add_argument(
        "host",
        choices=("claude", "codex", "gemini", "agy"),
        help="Target host. AGY is a placeholder until config format is confirmed.",
    )
    p_install.add_argument(
        "host_args",
        nargs=argparse.REMAINDER,
        help="Forwarded to the per-host installer (e.g. --repo, --dry-run, --skip-smoke-test).",
    )

    p_update_bin = sub.add_parser(
        "update-bin",
        help="Reinstall the kbask binary from the latest (or pinned) GitHub Release.",
    )
    p_update_bin.add_argument(
        "--tag",
        help="Release tag to install (e.g. 0.1.1 or v0.1.1). Defaults to latest. Overrides $KBASK_TAG.",
    )
    p_update_bin.add_argument(
        "--repo",
        help="GitHub repo in owner/name form. Defaults to sughosh-pocketfm/kbask. Overrides $KBASK_REPO.",
    )
    p_update_bin.add_argument(
        "--dry-run", action="store_true",
        help="Resolve the release and report planned actions without downloading or installing.",
    )
    p_update_bin.add_argument(
        "--skip-verify", action="store_true",
        help="Install even if the release has no SHA256SUMS asset (not recommended).",
    )

    sub.add_parser("health", help="Print backend versions and graph freshness.")

    p_doctor = sub.add_parser("doctor", help="Check that graphifyy and understand-anything are ready.")
    p_doctor.add_argument("repo", nargs="?", default=".", help="Repo root. Defaults to cwd.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "serve":
        from kbask.serve import run

        return run(Path(args.out_dir).resolve())

    if args.command == "update":
        from kbask.update import run

        return run(
            repo=Path(args.repo).resolve(),
            force=args.force,
            dry_run=args.dry_run,
            structural_only=args.structural_only,
        )

    if args.command == "install":
        from kbask.install import run

        return run(host=args.host, extra_args=args.host_args)

    if args.command == "update-bin":
        from kbask.update_bin import run

        return run(
            tag=args.tag,
            repo=args.repo,
            dry_run=args.dry_run,
            skip_verify=args.skip_verify,
        )

    if args.command == "health":
        from kbask.health import run

        return run()

    if args.command == "doctor":
        from kbask.doctor import run

        return run(Path(args.repo).resolve())

    return 2


if __name__ == "__main__":
    sys.exit(main())
