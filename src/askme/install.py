"""`askme install <host>` — dispatch to the per-host installer script bundled with the package."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path


logger = logging.getLogger("askme.install")


SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"


def run(host: str, repo: Path, dry_run: bool) -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="askme: %(message)s")
    script = SCRIPTS_DIR / f"install-{host}.py"
    if not script.exists():
        logger.error("installer not found: %s", script)
        return 1

    cmd = [sys.executable, str(script), "--repo", str(repo)]
    if dry_run:
        cmd.append("--dry-run")

    return subprocess.run(cmd).returncode
