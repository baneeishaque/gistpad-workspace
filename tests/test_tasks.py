"""Tests for Zed task and workspace README generation."""

from __future__ import annotations

import json

from gistpad_workspace import tasks


def test_render_tasks_is_valid_json_with_expected_tasks():
    parsed = json.loads(tasks.render_tasks())
    labels = [task["label"] for task in parsed]
    assert labels[0] == "Gist: Sync all"
    assert len(labels) == 10
    push = next(task for task in parsed if task["label"] == "Gist: Push current gist")
    assert "$ZED_FILE" in push["command"]


def test_write_if_changed_is_idempotent(tmp_path):
    path = tmp_path / "nested" / "tasks.json"
    assert tasks.write_if_changed(path, "content") is True
    assert tasks.write_if_changed(path, "content") is False
    assert path.read_text(encoding="utf-8") == "content"


def test_workspace_readme_mentions_requirements():
    readme = tasks.render_workspace_readme()
    assert "GITHUB_TOKEN" in readme
    assert "Gist: Sync all" in readme
