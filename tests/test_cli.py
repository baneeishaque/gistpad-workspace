"""Tests for the CLI (API client, git, and config mocked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gistpad_workspace import cli
from gistpad_workspace import git as git_module
from gistpad_workspace.manifest import load_manifest, save_manifest

GIST_ID = "abcdef1234567890"
DIR_NAME = "notes--abcdef12"


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.gists = []
        self.source = None
        self.user = {"login": "tester"}

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def list_gists(self):
        self._record("list_gists")
        return self.gists

    def list_starred(self):
        self._record("list_starred")
        return []

    def get_user(self):
        self._record("get_user")
        return self.user

    def get_gist(self, gist_id):
        self._record("get_gist", gist_id)
        return self.source

    def create_gist(self, files, description=None, public=False):
        self._record("create_gist", files, description, public)
        return {
            "id": "cafe1234cafe1234",
            "description": description,
            "public": public,
            "updated_at": "2026-10-03T00:00:00Z",
            "files": {name: {"filename": name} for name in files},
        }

    def update_gist(self, gist_id, description):
        self._record("update_gist", gist_id, description)
        return {}

    def update_gist_files(self, gist_id, files):
        self._record("update_gist_files", gist_id, files)
        return {}

    def delete_gist(self, gist_id):
        self._record("delete_gist", gist_id)

    def star_gist(self, gist_id):
        self._record("star_gist", gist_id)

    def unstar_gist(self, gist_id):
        self._record("unstar_gist", gist_id)

    def list_comments(self, gist_id):
        self._record("list_comments", gist_id)
        return []

    def create_comment(self, gist_id, body):
        self._record("create_comment", gist_id, body)
        return {"id": "c1"}

    def update_comment(self, gist_id, comment_id, body):
        self._record("update_comment", gist_id, comment_id, body)

    def delete_comment(self, gist_id, comment_id):
        self._record("delete_comment", gist_id, comment_id)


def make_gist(
    gist_id=GIST_ID,
    description="Notes",
    updated="2026-10-03T00:00:00Z",
    public=False,
    files=("a.md",),
):
    return {
        "id": gist_id,
        "description": description,
        "public": public,
        "updated_at": updated,
        "files": {name: {"filename": name} for name in files},
    }


def manifest_entry(
    gist_id=GIST_ID,
    dir_name=DIR_NAME,
    description="Notes",
    starred=False,
    archived=False,
):
    return {
        "id": gist_id,
        "description": description,
        "dir": dir_name,
        "public": False,
        "starred": starred,
        "archived": archived,
        "updated_at": "2026-10-03T00:00:00Z",
        "files": ["a.md"],
    }


def seed_manifest(root, gists):
    save_manifest(
        root,
        {
            "version": 1,
            "synced_at": None,
            "daily_gist_id": None,
            "prompts_gist_id": None,
            "gists": gists,
        },
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    config = {"workspace_root": str(tmp_path), "auto_rename": True, "auto_prune": False}
    monkeypatch.setattr(cli, "load_config", lambda: dict(config))
    fake = FakeClient()
    monkeypatch.setattr(cli, "GitHubClient", lambda *args, **kwargs: fake)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(git_module, "is_dirty", lambda repo: False)
    monkeypatch.setattr(
        git_module, "clone", lambda gist_id, dest, env=None: Path(dest).mkdir(parents=True)
    )
    monkeypatch.setattr(git_module, "fetch", lambda repo, env=None: None)
    monkeypatch.setattr(git_module, "pull_ff_only", lambda repo, env=None: None)
    monkeypatch.setattr(git_module, "ahead_behind", lambda repo: (0, 0))
    return SimpleNamespace(root=tmp_path, fake=fake)


def test_parser_requires_a_command():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_url_with_path(env, capsys):
    (env.root / DIR_NAME).mkdir()
    seed_manifest(env.root, [manifest_entry()])

    rc = cli.main(["url", "--path", str(env.root / DIR_NAME / "a.md")])

    assert rc == 0
    assert capsys.readouterr().out.strip() == f"https://gist.github.com/{GIST_ID}"


def test_list_shows_flags(env, capsys):
    seed_manifest(
        env.root,
        [
            manifest_entry(starred=True, archived=True),
            manifest_entry(
                gist_id="1111111122223333", dir_name="other--11111111", description="Other"
            ),
        ],
    )

    rc = cli.main(["list"])

    out = capsys.readouterr().out
    assert rc == 0
    assert DIR_NAME in out
    assert "SA" in out
    assert "other--11111111" in out


def test_star_toggle(env, capsys):
    (env.root / DIR_NAME).mkdir()
    seed_manifest(env.root, [manifest_entry()])

    rc = cli.main(["star", "--toggle", "--path", str(env.root / DIR_NAME / "a.md")])

    assert rc == 0
    assert ("star_gist", (GIST_ID,), {}) in env.fake.calls
    assert load_manifest(env.root)["gists"][0]["starred"] is True


def test_rename_updates_description_and_dir(env, capsys):
    (env.root / DIR_NAME).mkdir()
    seed_manifest(env.root, [manifest_entry()])

    rc = cli.main(["rename", "notes", "New Title"])

    assert rc == 0
    assert ("update_gist", (GIST_ID, "New Title"), {}) in env.fake.calls
    assert not (env.root / DIR_NAME).exists()
    assert (env.root / "new-title--abcdef12").exists()
    assert load_manifest(env.root)["gists"][0]["dir"] == "new-title--abcdef12"


def test_rename_preserves_archived_suffix(env):
    (env.root / DIR_NAME).mkdir()
    seed_manifest(
        env.root,
        [manifest_entry(description="Notes [Archived]", archived=True)],
    )

    rc = cli.main(["rename", "notes", "New Title"])

    assert rc == 0
    assert ("update_gist", (GIST_ID, "New Title [Archived]"), {}) in env.fake.calls


def test_create_registers_and_clones(env, capsys):
    rc = cli.main(["create", "--description", "Idea", "--file", "a.md=hello"])

    assert rc == 0
    assert (
        "create_gist",
        ({"a.md": "hello"}, "Idea", False),
        {},
    ) in env.fake.calls
    assert (env.root / "idea--cafe1234").exists()
    manifest = load_manifest(env.root)
    assert manifest["gists"][0]["dir"] == "idea--cafe1234"


def test_create_empty_file_uses_sentinel(env):
    rc = cli.main(["create", "--description", "Blank", "--file", "b.md="])

    assert rc == 0
    files = env.fake.calls[0][1][0]
    assert files == {"b.md": "\u2064"}


def test_delete_moves_dir_to_trash(env):
    (env.root / DIR_NAME).mkdir()
    seed_manifest(env.root, [manifest_entry()])

    rc = cli.main(["delete", "notes", "--yes"])

    assert rc == 0
    assert ("delete_gist", (GIST_ID,), {}) in env.fake.calls
    assert not (env.root / DIR_NAME).exists()
    assert list((env.root / ".gistpad-workspace" / "trash").glob(f"*/{DIR_NAME}"))
    assert load_manifest(env.root)["gists"] == []


def test_archive_refuses_daily_gist(env, capsys):
    seed_manifest(
        env.root,
        [manifest_entry(description="📆 Daily notes")],
    )

    rc = cli.main(["archive", "daily"])

    assert rc == 1
    assert "cannot be archived" in capsys.readouterr().err


def test_duplicate_copies_files(env, capsys):
    env.fake.source = {
        "id": GIST_ID,
        "description": "Notes",
        "public": False,
        "files": {"a.md": {"content": "hi"}},
    }
    seed_manifest(env.root, [manifest_entry()])

    rc = cli.main(["duplicate", "notes"])

    assert rc == 0
    assert (
        "create_gist",
        ({"a.md": "hi"}, "Notes (Copy)", False),
        {},
    ) in env.fake.calls
    manifest = load_manifest(env.root)
    duplicated = next(g for g in manifest["gists"] if g["id"] == "cafe1234cafe1234")
    assert duplicated["description"] == "Notes (Copy)"


def test_comment_add_with_body(env, capsys):
    seed_manifest(env.root, [manifest_entry()])

    rc = cli.main(["comment", "add", "notes", "hello there"])

    assert rc == 0
    assert ("create_comment", (GIST_ID, "hello there"), {}) in env.fake.calls
    assert "comment c1 created" in capsys.readouterr().out


def test_push_all_reports_nothing(env, capsys):
    (env.root / DIR_NAME).mkdir()
    seed_manifest(env.root, [manifest_entry()])

    rc = cli.main(["push", "--all"])

    assert rc == 0
    assert "nothing to push" in capsys.readouterr().out


def test_sync_dry_run(env, capsys):
    env.fake.gists = [make_gist()]

    rc = cli.main(["sync", "--dry-run"])

    assert rc == 0
    assert "cloned: notes--abcdef12" in capsys.readouterr().out


def test_daily_creates_gist_and_file(env, capsys):
    rc = cli.main(["daily", "--date", "2026-10-03"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "2026-10-03.md" in out
    manifest = load_manifest(env.root)
    assert manifest["daily_gist_id"] == "cafe1234cafe1234"
    assert (env.root / "daily-notes--cafe1234" / "2026-10-03.md").exists()


def test_status_empty_manifest(env, capsys):
    rc = cli.main(["status"])

    assert rc == 0
    assert "No gists in the manifest" in capsys.readouterr().out


def test_doctor_reports_checks(env, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="git version 2.x", returncode=0),
    )

    rc = cli.main(["doctor"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "ok: token from GITHUB_TOKEN environment variable" in out
    assert "ok: GitHub API reachable as tester" in out


def test_doctor_reports_token_file_and_permissions(env, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    token_path = env.root / ".gistpad-workspace" / "token"
    token_path.parent.mkdir(parents=True)
    token_path.write_text("file-token\n", encoding="utf-8")
    token_path.chmod(0o644)
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="git version 2.x", returncode=0),
    )

    rc = cli.main(["doctor"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "ok: token from token file" in out
    assert "chmod 600" in out


def test_doctor_fails_without_token(env, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="git version 2.x", returncode=0),
    )

    rc = cli.main(["doctor"])

    out = capsys.readouterr().out
    assert rc == 1
    assert "fail: no token found" in out


def test_main_reports_errors(env, capsys):
    rc = cli.main(["url", "missing-gist"])

    assert rc == 1
    assert "No gist matches" in capsys.readouterr().err
