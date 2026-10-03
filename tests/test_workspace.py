"""Tests for the workspace engine (git calls and API client mocked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gistpad_workspace import git
from gistpad_workspace.errors import GistpadError
from gistpad_workspace.manifest import load_manifest, save_manifest
from gistpad_workspace.workspace import Workspace

GIST_ID = "abcdef1234567890"
DIR_NAME = "notes--abcdef12"


class FakeClient:
    def __init__(self, gists, starred=None):
        self._gists = gists
        self._starred = starred or []

    def list_gists(self):
        return self._gists

    def list_starred(self):
        return self._starred


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
    updated="2026-10-03T00:00:00Z",
):
    return {
        "id": gist_id,
        "description": description,
        "dir": dir_name,
        "public": False,
        "starred": False,
        "archived": False,
        "updated_at": updated,
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


def make_workspace(tmp_path, gists, starred=None, auto_rename=True, auto_prune=False):
    config = {
        "workspace_root": str(tmp_path),
        "auto_rename": auto_rename,
        "auto_prune": auto_prune,
    }
    return Workspace(tmp_path, config=config, client=FakeClient(gists, starred))


@pytest.fixture
def git_stub(monkeypatch):
    calls = SimpleNamespace(
        clones=[], fetches=[], pulls=[], pushes=[], commits=[], dirty=False, ahead=0, behind=0
    )

    def clone(gist_id, dest):
        calls.clones.append((gist_id, str(dest)))
        Path(dest).mkdir(parents=True)

    monkeypatch.setattr(git, "clone", clone)
    monkeypatch.setattr(git, "fetch", lambda repo: calls.fetches.append(str(repo)))
    monkeypatch.setattr(git, "pull_ff_only", lambda repo: calls.pulls.append(str(repo)))
    monkeypatch.setattr(git, "is_dirty", lambda repo: calls.dirty)
    monkeypatch.setattr(git, "ahead_behind", lambda repo: (calls.ahead, calls.behind))
    monkeypatch.setattr(
        git,
        "commit_all",
        lambda repo, message: calls.commits.append((str(repo), message)) or True,
    )
    monkeypatch.setattr(git, "push", lambda repo: calls.pushes.append(str(repo)))
    return calls


def test_sync_clones_new_gist(tmp_path, git_stub):
    ws = make_workspace(tmp_path, [make_gist()], starred=[{"id": GIST_ID}])
    summary = ws.sync()

    assert summary.cloned == [DIR_NAME]
    assert git_stub.clones == [(GIST_ID, str(tmp_path / DIR_NAME))]
    manifest = load_manifest(tmp_path)
    assert manifest["gists"][0]["dir"] == DIR_NAME
    assert manifest["gists"][0]["starred"] is True
    assert (tmp_path / ".zed" / "tasks.json").exists()
    assert (tmp_path / "README.md").exists()


def test_sync_pulls_updated_clean_gist(tmp_path, git_stub):
    (tmp_path / DIR_NAME).mkdir()
    seed_manifest(tmp_path, [manifest_entry()])
    ws = make_workspace(tmp_path, [make_gist(updated="2026-10-04T00:00:00Z")])
    git_stub.behind = 1

    summary = ws.sync()

    assert summary.pulled == [DIR_NAME]
    assert git_stub.fetches == [str(tmp_path / DIR_NAME)]
    assert git_stub.pulls == [str(tmp_path / DIR_NAME)]
    assert load_manifest(tmp_path)["gists"][0]["updated_at"] == "2026-10-04T00:00:00Z"


def test_sync_skips_dirty_updated_gist(tmp_path, git_stub):
    (tmp_path / DIR_NAME).mkdir()
    seed_manifest(tmp_path, [manifest_entry()])
    ws = make_workspace(tmp_path, [make_gist(updated="2026-10-04T00:00:00Z")])
    git_stub.dirty = True

    summary = ws.sync()

    assert summary.skipped_dirty == [DIR_NAME]
    assert git_stub.fetches == []


def test_sync_auto_renames_on_description_change(tmp_path, git_stub):
    old_dir = "old-title--abcdef12"
    (tmp_path / old_dir).mkdir()
    seed_manifest(tmp_path, [manifest_entry(dir_name=old_dir, description="Old Title")])
    ws = make_workspace(tmp_path, [make_gist(description="New Title")])

    summary = ws.sync()

    assert summary.renamed == [(old_dir, "new-title--abcdef12")]
    assert not (tmp_path / old_dir).exists()
    assert (tmp_path / "new-title--abcdef12").exists()
    assert load_manifest(tmp_path)["gists"][0]["dir"] == "new-title--abcdef12"


def test_sync_defers_rename_when_dirty(tmp_path, git_stub):
    old_dir = "old-title--abcdef12"
    (tmp_path / old_dir).mkdir()
    seed_manifest(tmp_path, [manifest_entry(dir_name=old_dir, description="Old Title")])
    ws = make_workspace(tmp_path, [make_gist(description="New Title")])
    git_stub.dirty = True

    summary = ws.sync()

    assert summary.deferred_renames == [old_dir]
    assert (tmp_path / old_dir).exists()
    assert load_manifest(tmp_path)["gists"][0]["dir"] == old_dir


def test_sync_prune_trashes_removed_gist(tmp_path, git_stub):
    gone_dir = "gone--deadbeef"
    (tmp_path / gone_dir).mkdir()
    seed_manifest(tmp_path, [manifest_entry(gist_id="deadbeef00000000", dir_name=gone_dir)])
    ws = make_workspace(tmp_path, [])

    summary = ws.sync(prune=True)

    assert summary.removed == [gone_dir]
    assert summary.pruned == [gone_dir]
    assert not (tmp_path / gone_dir).exists()
    trashed = list((tmp_path / ".gistpad-workspace" / "trash").glob(f"*/{gone_dir}"))
    assert len(trashed) == 1
    assert load_manifest(tmp_path)["gists"] == []


def test_sync_dry_run_makes_no_changes(tmp_path, git_stub):
    ws = make_workspace(tmp_path, [make_gist()])

    summary = ws.sync(dry_run=True)

    assert summary.cloned == [DIR_NAME]
    assert git_stub.clones == []
    assert not (tmp_path / DIR_NAME).exists()
    assert not (tmp_path / ".gistpad-workspace" / "manifest.json").exists()
    assert not (tmp_path / ".zed" / "tasks.json").exists()


def test_resolve_by_id_prefix_dir_and_description(tmp_path):
    other = manifest_entry(
        gist_id="1111111122223333", dir_name="other--11111111", description="Other"
    )
    ws = make_workspace(tmp_path, [])
    ws.manifest["gists"] = [manifest_entry(), other]

    assert ws.resolve(GIST_ID)["dir"] == DIR_NAME
    assert ws.resolve("abcdef12")["dir"] == DIR_NAME
    assert ws.resolve(DIR_NAME)["dir"] == DIR_NAME
    assert ws.resolve("othe")["dir"] == "other--11111111"


def test_resolve_rejects_ambiguous_and_unknown(tmp_path):
    ws = make_workspace(tmp_path, [])
    ws.manifest["gists"] = [manifest_entry(), manifest_entry(gist_id="9999999988887777")]

    with pytest.raises(GistpadError, match="ambiguous"):
        ws.resolve("notes")
    with pytest.raises(GistpadError, match="No gist matches"):
        ws.resolve("zzz")


def test_resolve_by_path(tmp_path):
    (tmp_path / DIR_NAME).mkdir()
    ws = make_workspace(tmp_path, [])
    ws.manifest["gists"] = [manifest_entry()]

    entry = ws.resolve_by_path(str(tmp_path / DIR_NAME / "a.md"))
    assert entry["id"] == GIST_ID

    with pytest.raises(GistpadError, match="not inside the workspace root"):
        ws.resolve_by_path(str(tmp_path.parent / "elsewhere.md"))


def test_push_commits_and_pushes(tmp_path, git_stub):
    (tmp_path / DIR_NAME).mkdir()
    ws = make_workspace(tmp_path, [])
    ws.manifest["gists"] = [manifest_entry()]
    git_stub.dirty = True
    git_stub.ahead = 1

    results = ws.push(selector="notes")

    assert results == [(DIR_NAME, "pushed")]
    assert git_stub.commits == [(str(tmp_path / DIR_NAME), "Update via gistpad-workspace")]
    assert git_stub.pushes == [str(tmp_path / DIR_NAME)]


def test_push_nothing_when_clean_and_synced(tmp_path, git_stub):
    (tmp_path / DIR_NAME).mkdir()
    ws = make_workspace(tmp_path, [])
    ws.manifest["gists"] = [manifest_entry()]

    results = ws.push(push_all=True)

    assert results == [(DIR_NAME, "nothing to push")]
    assert git_stub.pushes == []


def test_push_requires_a_target(tmp_path):
    ws = make_workspace(tmp_path, [])
    ws.manifest["gists"] = [manifest_entry()]

    with pytest.raises(GistpadError, match="Specify a gist"):
        ws.push()


def test_status_reports_states(tmp_path, git_stub):
    (tmp_path / DIR_NAME).mkdir()
    ws = make_workspace(tmp_path, [])
    ws.manifest["gists"] = [manifest_entry()]

    git_stub.dirty = True
    assert ws.status()[0]["state"] == "dirty"

    git_stub.dirty = False
    git_stub.ahead = 2
    assert ws.status()[0]["state"] == "ahead +2"

    git_stub.ahead = 0
    assert ws.status()[0]["state"] == "clean"

    (tmp_path / DIR_NAME).rmdir()
    assert ws.status()[0]["state"] == "missing"


def test_init_writes_config_tasks_and_readme(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    ws = make_workspace(tmp_path, [])

    actions = ws.init()

    assert any("config" in action for action in actions)
    assert (tmp_path / "xdg" / "gistpad-workspace" / "config.json").exists()
    assert (tmp_path / ".zed" / "tasks.json").exists()
    assert (tmp_path / "README.md").exists()
    assert (tmp_path / ".gistpad-workspace" / "manifest.json").exists()
