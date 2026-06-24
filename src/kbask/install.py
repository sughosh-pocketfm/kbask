"""`kbask install <host>` — in-process dispatcher to per-host installers.

Each installer module under `kbask.installers` exposes:
  - `add_arguments(parser)`: register host-specific CLI flags
  - `main(args)`: do the install, return exit code

This module owns argparse construction so the same CLI works when invoked
via a local clone, a `pip install`, or `uvx --from git+https://...`.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from typing import Sequence


logger = logging.getLogger("kbask.install")


HOSTS = ("claude", "codex", "gemini", "agy")


def _module(host: str):
    return importlib.import_module(f"kbask.installers.{host}")


def run(host: str, extra_args: Sequence[str] | None = None) -> int:
    """Run the installer for `host`, forwarding `extra_args` to its argparse."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="kbask: %(message)s")
    if host not in HOSTS:
        logger.error("unknown host %r; choose from %s", host, ", ".join(HOSTS))
        return 1
    mod = _module(host)
    parser = argparse.ArgumentParser(prog=f"kbask install {host}")
    mod.add_arguments(parser)
    ns = parser.parse_args(list(extra_args or []))
    return mod.main(ns)
