"""Workspace-scoped token resolution (multi-account friendly).

Resolution order:

1. ``GITHUB_TOKEN`` environment variable (wins, useful for per-shell overrides)
2. ``<workspace>/.gistpad-workspace/token`` file (one token per workspace, so
   different workspaces can use different GitHub accounts)
"""

from __future__ import annotations

import os
from pathlib import Path

TOKEN_FILE_NAME = "token"


def token_file_path(root: Path) -> Path:
    return root / ".gistpad-workspace" / TOKEN_FILE_NAME


def resolve_token(root: Path) -> tuple[str | None, str | None]:
    """Return ``(token, source)``; ``source`` describes where the token came from."""
    env_token = os.environ.get("GITHUB_TOKEN")
    if env_token:
        return env_token, "GITHUB_TOKEN environment variable"
    path = token_file_path(root)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value, f"token file {path}"
    return None, None
