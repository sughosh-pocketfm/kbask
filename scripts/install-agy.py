#!/usr/bin/env python3
"""Install askme MCP server into AGY host config.

STATUS: NOT YET IMPLEMENTED.

The config-file path and format for AGY hosts is not yet documented in
this project. To enable AGY support:

  1. Confirm the AGY config file location (analogous to ~/.codex/config.toml
     for Codex or ~/.gemini/settings.json for Gemini).
  2. Confirm the config format (JSON, TOML, YAML, custom).
  3. Confirm the schema for declaring an MCP server entry.
  4. Mirror install-codex.py or install-gemini.py here.

Open an issue on https://github.com/sughosh-pocketfm/ask-me when the above
is known.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "AGY installer not yet implemented. The config path and format are not "
        "documented in this project. See scripts/install-agy.py header for the "
        "checklist of what's needed to enable it.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
