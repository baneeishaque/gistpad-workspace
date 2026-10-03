"""Workspace manifest: durable sync state under ``.gistpad-workspace/``."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1
MANIFEST_DIR = ".gistpad-workspace"
MANIFEST_NAME = "manifest.json"


def manifest_path(root: Path) -> Path:
    return root / MANIFEST_DIR / MANIFEST_NAME


def empty_manifest() -> dict[str, Any]:
    return {
        "version": MANIFEST_VERSION,
        "synced_at": None,
        "daily_gist_id": None,
        "prompts_gist_id": None,
        "gists": [],
    }


def load_manifest(root: Path) -> dict[str, Any]:
    path = manifest_path(root)
    manifest = empty_manifest()
    if path.exists():
        manifest.update(json.loads(path.read_text(encoding="utf-8")))
    return manifest


def save_manifest(root: Path, manifest: dict[str, Any]) -> Path:
    manifest["synced_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def gists_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {gist["id"]: gist for gist in manifest["gists"]}
