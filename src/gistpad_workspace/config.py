"""Workspace configuration file handling."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "workspace_root": "~/Gists",
    "auto_rename": True,
    "auto_prune": False,
}


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "gistpad-workspace"


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config(path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    config = dict(DEFAULTS)
    if target.exists():
        config.update(json.loads(target.read_text(encoding="utf-8")))
    return config


def save_config(config: dict[str, Any], path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return target


def workspace_root(config: dict[str, Any]) -> Path:
    return Path(str(config["workspace_root"])).expanduser()
