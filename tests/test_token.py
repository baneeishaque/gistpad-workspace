"""Tests for workspace-scoped token resolution."""

from __future__ import annotations

from gistpad_workspace.token import resolve_token, token_file_path


def test_env_wins_over_token_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    path = token_file_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("file-token\n", encoding="utf-8")

    token, source = resolve_token(tmp_path)

    assert token == "env-token"
    assert "environment" in source


def test_token_file_used_when_env_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    path = token_file_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("  file-token\n", encoding="utf-8")

    token, source = resolve_token(tmp_path)

    assert token == "file-token"
    assert "token file" in source


def test_no_token_anywhere(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert resolve_token(tmp_path) == (None, None)


def test_blank_token_file_ignored(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    path = token_file_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("\n", encoding="utf-8")

    assert resolve_token(tmp_path) == (None, None)
