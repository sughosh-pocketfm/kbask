"""`kbask update-bin` — refresh the kbask binary from a GitHub Release.

Downloads the wheel attached to a GitHub Release, verifies it against
`SHA256SUMS`, then installs it via `uv tool install --force`. Equivalent
to the one-line `tool-install.sh` curl bootstrap but callable from an
already-installed `kbask` without leaving the terminal.

Resolution order for the target tag:
  1. explicit `--tag X.Y.Z` argument.
  2. `$KBASK_TAG` environment variable.
  3. GitHub `releases/latest` API.

The repo is configurable via `--repo owner/name` or `$KBASK_REPO`,
defaulting to the upstream fork at `sughosh-pocketfm/kbask`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


logger = logging.getLogger("kbask.update_bin")

DEFAULT_REPO = "sughosh-pocketfm/kbask"
USER_AGENT = "kbask-update-bin"


class UpdateBinError(RuntimeError):
    pass


# ------------------------------------------------------------------
# GitHub API helpers
# ------------------------------------------------------------------

def _api_get(url: str, token: Optional[str]) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise UpdateBinError(f"GitHub API {url} returned {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise UpdateBinError(f"GitHub API {url} unreachable: {exc.reason}") from exc


def _resolve_release(repo: str, tag: Optional[str], token: Optional[str]) -> dict:
    if tag:
        url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    else:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
    return _api_get(url, token)


def _pick_asset(release: dict, suffix: str) -> dict:
    for asset in release.get("assets") or []:
        name = asset.get("name") or ""
        if name.endswith(suffix):
            return asset
    raise UpdateBinError(
        f"release {release.get('tag_name')!r} has no asset matching *{suffix}"
    )


def _download(url: str, dest: Path, token: Optional[str]) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_sumsfile(text: str) -> dict[str, str]:
    """Parse `shasum -a 256` output → {filename: hex}."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Format: "<sha>  <filename>" or "<sha> *<filename>".
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        sha, name = parts
        name = name.lstrip("*").strip()
        out[name] = sha
    return out


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def run(
    tag: Optional[str] = None,
    repo: Optional[str] = None,
    dry_run: bool = False,
    skip_verify: bool = False,
) -> int:
    logging.basicConfig(level=logging.INFO, format="kbask: %(message)s")

    repo = repo or os.environ.get("KBASK_REPO") or DEFAULT_REPO
    tag = tag or os.environ.get("KBASK_TAG")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    uv = shutil.which("uv")
    if uv is None:
        logger.error("uv not found on PATH. Install via https://docs.astral.sh/uv/ first.")
        return 1

    try:
        release = _resolve_release(repo, tag, token)
    except UpdateBinError as exc:
        logger.error("%s", exc)
        return 1

    resolved_tag = release.get("tag_name") or "unknown"
    logger.info("resolved release: %s @ %s", repo, resolved_tag)

    try:
        wheel_asset = _pick_asset(release, ".whl")
    except UpdateBinError as exc:
        logger.error("%s", exc)
        return 1

    sums_asset: Optional[dict]
    try:
        sums_asset = _pick_asset(release, "SHA256SUMS")
    except UpdateBinError:
        sums_asset = None
        if not skip_verify:
            logger.error(
                "release %s has no SHA256SUMS asset; pass --skip-verify to install anyway",
                resolved_tag,
            )
            return 1

    if dry_run:
        logger.info("dry-run: would install %s from %s", wheel_asset["name"], wheel_asset["browser_download_url"])
        if sums_asset:
            logger.info("dry-run: would verify against %s", sums_asset["name"])
        return 0

    with tempfile.TemporaryDirectory(prefix="kbask-update-bin-") as tmp:
        tmp_path = Path(tmp)
        wheel_path = tmp_path / wheel_asset["name"]
        logger.info("downloading %s", wheel_asset["name"])
        try:
            _download(wheel_asset["browser_download_url"], wheel_path, token)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            logger.error("download failed: %s", exc)
            return 1

        if sums_asset and not skip_verify:
            sums_path = tmp_path / sums_asset["name"]
            logger.info("downloading %s", sums_asset["name"])
            try:
                _download(sums_asset["browser_download_url"], sums_path, token)
            except (urllib.error.HTTPError, urllib.error.URLError) as exc:
                logger.error("checksum download failed: %s", exc)
                return 1

            expected = _parse_sumsfile(sums_path.read_text(encoding="utf-8")).get(wheel_path.name)
            if expected is None:
                logger.error("SHA256SUMS has no entry for %s", wheel_path.name)
                return 1
            actual = _sha256(wheel_path)
            if actual.lower() != expected.lower():
                logger.error(
                    "checksum mismatch for %s\n  expected: %s\n  actual:   %s",
                    wheel_path.name, expected, actual,
                )
                return 1
            logger.info("sha256 verified: %s", actual[:12])

        cmd = [uv, "tool", "install", "--force", str(wheel_path)]
        logger.info("running: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        if proc.returncode != 0:
            logger.error("uv tool install failed (rc=%s)", proc.returncode)
            return proc.returncode

    logger.info("kbask %s installed. Restart your MCP host to pick it up.", resolved_tag)
    return 0
