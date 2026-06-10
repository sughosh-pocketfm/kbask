#!/usr/bin/env bash
# kbask persistent CLI installer.
#
# One-liner:
#   curl -fsSL https://raw.githubusercontent.com/sughosh-pocketfm/kbask/main/tool-install.sh | bash
#
# Installs `kbask` via `uv tool install` so the binary is available on PATH
# (under $HOME/.local/bin by default). Prefers the latest GitHub Release
# wheel; falls back to building from git if no release exists yet.
#
# Env:
#   KBASK_TAG       pin a specific release tag (e.g. 0.1.0). Default: latest.
#   KBASK_SOURCE    override the `uv tool install` source entirely.
#                   Examples:
#                     - kbask                                          # PyPI
#                     - git+https://github.com/sughosh-pocketfm/kbask  # git HEAD
#                     - git+https://github.com/sughosh-pocketfm/kbask@0.1.0
#                     - /local/path/to/wheel.whl
#   KBASK_REPO      GitHub repo slug. Default: sughosh-pocketfm/kbask.

set -euo pipefail

REPO="${KBASK_REPO:-sughosh-pocketfm/kbask}"
say() { printf '[kbask] %s\n' "$*" >&2; }

# 1. Ensure uv is on PATH.
if ! command -v uv >/dev/null 2>&1; then
  say "uv not found; installing via Astral's installer"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# 2. Resolve install source.
SOURCE="${KBASK_SOURCE:-}"
if [ -z "$SOURCE" ]; then
  TAG="${KBASK_TAG:-}"
  if [ -z "$TAG" ] && command -v curl >/dev/null 2>&1; then
    TAG="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null \
      | grep -E '"tag_name"' | head -1 | sed -E 's/.*"tag_name"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/' || true)"
  fi

  if [ -n "$TAG" ]; then
    # Try to grab the wheel URL from the release.
    WHEEL_URL="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/tags/${TAG}" 2>/dev/null \
      | grep -E '"browser_download_url"' \
      | grep -E '\.whl"' \
      | head -1 \
      | sed -E 's/.*"browser_download_url"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/' || true)"
    if [ -n "$WHEEL_URL" ]; then
      SOURCE="$WHEEL_URL"
      say "using release wheel: $TAG"
    else
      SOURCE="git+https://github.com/${REPO}@${TAG}"
      say "using git source pinned to $TAG"
    fi
  else
    SOURCE="git+https://github.com/${REPO}"
    say "no release found; using git HEAD"
  fi
fi

# 3. Install.
say "uv tool install $SOURCE"
uv tool install --force "$SOURCE"

# 4. Verify.
KBASK="$(command -v kbask || true)"
if [ -z "$KBASK" ]; then
  KBASK="$(uv tool dir 2>/dev/null)/kbask/bin/kbask"
fi
if [ -x "$KBASK" ]; then
  say "installed: $KBASK"
  "$KBASK" --help | head -6
else
  say "WARN: kbask not on PATH yet. Add \$HOME/.local/bin to your PATH and rerun a shell."
  echo 'export PATH="$HOME/.local/bin:$PATH"' >&2
fi

cat >&2 <<'EOF'

Next steps:
  kbask install claude --repo .     # wire MCP into Claude Code
  kbask install codex  --repo .     # or Codex
  kbask install gemini --repo .     # or Gemini
  kbask update .                    # build/refresh knowledge graph
  kbask --help                      # full surface

Upgrade later:
  uv tool upgrade kbask             # or rerun this script
EOF
