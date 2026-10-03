"""Generation of Zed tasks and the managed workspace README."""

from __future__ import annotations

import json
from pathlib import Path

TASK_DEFINITIONS: list[dict[str, object]] = [
    {
        "label": "Gist: Sync all",
        "command": "gistpad-workspace sync",
        "reveal": "no_focus",
        "hide": "on_success",
    },
    {
        "label": "Gist: Status",
        "command": "gistpad-workspace status",
        "reveal": "always",
        "hide": "never",
    },
    {
        "label": "Gist: Push all",
        "command": "gistpad-workspace push --all",
        "reveal": "always",
    },
    {
        "label": "Gist: Push current gist",
        "command": 'gistpad-workspace push --path "$ZED_FILE"',
        "reveal": "no_focus",
    },
    {
        "label": "Gist: Open today's note",
        "command": "gistpad-workspace daily --open",
    },
    {
        "label": "Gist: Create…",
        "command": "gistpad-workspace create",
    },
    {
        "label": "Gist: Star/unstar current gist",
        "command": 'gistpad-workspace star --toggle --path "$ZED_FILE"',
    },
    {
        "label": "Gist: Archive/unarchive current gist",
        "command": 'gistpad-workspace archive --toggle --path "$ZED_FILE"',
    },
    {
        "label": "Gist: Comment on current gist",
        "command": 'gistpad-workspace comment add --path "$ZED_FILE"',
    },
    {
        "label": "Gist: Copy current gist URL",
        "command": 'gistpad-workspace url --path "$ZED_FILE"',
    },
]

WORKSPACE_README = """# Gists workspace

This folder is managed by [gistpad-workspace](https://github.com/baneeishaque/gistpad-workspace).
Each subfolder is a git clone of one GitHub gist; the root itself is not a repository, so Zed
activates every gist folder as a repository in its Git panel.

## Everyday flow

- Edit files in Zed, then run **Gist: Push current gist** (or push from Zed's Git panel).
- Run **Gist: Sync all** to clone new gists and pull remote updates.
- Run **Gist: Open today's note** for the daily note.

## Requirements

- A GitHub token (scope: `gist`), provided either as `GITHUB_TOKEN` in your
  environment or in `.gistpad-workspace/token` (one token per workspace, so
  multiple GitHub accounts stay separate).
- Tasks are defined in `.zed/tasks.json` (regenerated on sync).

## Notes

- Descriptions and metadata are tracked in `.gistpad-workspace/manifest.json`.
- Removed gists are reported on sync; `sync --prune` moves them to `.gistpad-workspace/trash/`.
- Directory names follow `<kebab-slug>--<id8>` and auto-rename when a gist description changes
  (only while the folder has no uncommitted changes).
"""


def render_tasks() -> str:
    return json.dumps(TASK_DEFINITIONS, indent=2) + "\n"


def render_workspace_readme() -> str:
    return WORKSPACE_README


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True
