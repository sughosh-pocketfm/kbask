"""Incremental update orchestrator: `askme update <repo>`."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List

from askme import __version__
from askme.backends import graphify, understand
from askme.diff import Delta, carry_forward, compute
from askme.meta import Meta, hash_file, load, now_iso, save


logger = logging.getLogger("askme.update")


# File extensions considered for per-file semantic indexing. Conservative
# default — keep aligned with Graphify's languages support.
SOURCE_EXTENSIONS = {
    ".kt", ".java", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rb",
    ".rs", ".cs", ".cpp", ".hpp", ".c", ".h", ".php", ".swift", ".m",
    ".mm", ".scala",
}


def _git_sha(repo: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _walk_sources(repo: Path) -> Iterable[Path]:
    """Yield source files Graphify would consider. Skips common vendor / build dirs."""
    skip = {".git", "node_modules", "build", "dist", ".gradle", "askme-out", "graphify-out", "venv", ".venv"}
    for path in repo.rglob("*"):
        if path.is_dir():
            continue
        if any(part in skip for part in path.relative_to(repo).parts):
            continue
        if path.suffix.lower() in SOURCE_EXTENSIONS:
            yield path


def _hash_repo(repo: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for path in _walk_sources(repo):
        rel = path.relative_to(repo).as_posix()
        out[rel] = hash_file(path)
    return out


def run(repo: Path, *, force: bool, dry_run: bool, structural_only: bool) -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="askme: %(message)s")

    out_dir = repo / "askme-out"
    graph_path = out_dir / "graph.json"
    knowledge_graph_path = out_dir / "knowledge-graph.json"
    meta_path = out_dir / "meta.json"

    previous = Meta() if force else load(meta_path)

    logger.info("scanning repo %s for source files", repo)
    current_hashes = _hash_repo(repo)
    delta = compute(previous, current_hashes)
    logger.info("delta: %s", delta.summary())

    if dry_run:
        _print_plan(delta, structural_only=structural_only)
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("running graphify update")
    try:
        graphify.update(repo=repo, graph_path=graph_path)
    except graphify.GraphifyUnavailable as exc:
        logger.error("structural backend failed: %s", exc)
        return 1

    if not structural_only:
        dirty_list = sorted(delta.dirty)
        logger.info("mirroring understand-anything knowledge graph (dirty=%d)", len(dirty_list))
        try:
            understand.update(
                repo=repo,
                knowledge_graph_path=knowledge_graph_path,
                dirty=dirty_list,
                full_rebuild=force,
            )
        except understand.UnderstandUnavailable as exc:
            # Soft-fail: structural index still useful on its own.
            logger.warning("semantic graph not available: %s", exc)

    new_files = carry_forward(previous, delta, current_hashes)
    new_meta = Meta(
        askme_version=__version__,
        graphify_version=graphify.version(),
        understand_version=understand.version(),
        git_sha=_git_sha(repo),
        built_at=now_iso(),
        files=new_files,
    )
    save(meta_path, new_meta)
    logger.info("wrote %s", meta_path)
    return 0


def _print_plan(delta: Delta, *, structural_only: bool) -> None:
    print("askme update plan (dry-run)")
    print(f"  added:     {len(delta.added)}")
    print(f"  modified:  {len(delta.modified)}")
    print(f"  removed:   {len(delta.removed)}")
    print(f"  unchanged: {len(delta.unchanged)}")
    print(f"  structural rebuild: yes")
    print(f"  semantic rebuild:   {'skipped (--structural-only)' if structural_only else f'{len(delta.dirty)} files'}")
