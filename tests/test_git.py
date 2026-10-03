"""Tests for the git wrapper (subprocess mocked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gistpad_workspace import git
from gistpad_workspace.errors import GistpadError


def test_auth_args_never_persist_credentials():
    args = git.auth_args()
    assert args[0] == "-c"
    assert args[1] == "credential.helper="
    assert args[2] == "-c"
    assert "credential.helper=!" in args[3]
    assert "$GITHUB_TOKEN" in args[3]


def test_run_git_raises_on_failure(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(git.subprocess, "run", fake_run)
    with pytest.raises(GistpadError, match="boom"):
        git.run_git(["status"])


def test_run_git_passes_through_on_success(monkeypatch):
    monkeypatch.setattr(
        git.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )
    result = git.run_git(["status"])
    assert result.stdout == "ok"


def test_run_git_forwards_env(monkeypatch):
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(git.subprocess, "run", fake_run)
    env = {"GITHUB_TOKEN": "x"}
    git.run_git(["status"], env=env)
    assert captured["env"] == env


def test_push_forwards_env(monkeypatch):
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(git.subprocess, "run", fake_run)
    env = {"GITHUB_TOKEN": "x"}
    git.push(Path("/repo"), env=env)
    assert captured["env"] == env
    assert captured["cwd"] == "/repo"


def test_is_dirty(monkeypatch):
    monkeypatch.setattr(
        git.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=" M a.md\n", stderr=""),
    )
    assert git.is_dirty(Path("/repo")) is True

    monkeypatch.setattr(
        git.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    assert git.is_dirty(Path("/repo")) is False


def test_ahead_behind_parses_counts(monkeypatch):
    monkeypatch.setattr(
        git.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="2\t3\n", stderr=""),
    )
    assert git.ahead_behind(Path("/repo")) == (3, 2)


def test_ahead_behind_without_upstream(monkeypatch):
    monkeypatch.setattr(
        git.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=128, stdout="", stderr="no upstream"),
    )
    assert git.ahead_behind(Path("/repo")) == (0, 0)
