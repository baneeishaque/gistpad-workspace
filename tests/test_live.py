"""Live integration tests against the real GitHub API (opt-in via ``--run-live``).

Requires ``GITHUB_TOKEN`` (scope: ``gist``). Creates scratch gists, exercises the
full lifecycle, and deletes every gist it created during teardown.
"""

from __future__ import annotations

import contextlib
import os
import uuid

import pytest

from gistpad_workspace import cli
from gistpad_workspace import conventions as conv
from gistpad_workspace.api import GitHubClient
from gistpad_workspace.errors import ApiError
from gistpad_workspace.workspace import Workspace

pytestmark = pytest.mark.live

NONCE = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def token():
    value = os.environ.get("GITHUB_TOKEN")
    if not value:
        pytest.skip("GITHUB_TOKEN is not set")
    return value


@pytest.fixture
def client(token):
    return GitHubClient()


@pytest.fixture
def cleanup(client):
    created: list[str] = []
    yield created
    for gist_id in created:
        with contextlib.suppress(ApiError):
            client.delete_gist(gist_id)


@pytest.fixture
def live_ws(tmp_path, client, monkeypatch):
    config = {"workspace_root": str(tmp_path), "auto_rename": True, "auto_prune": False}
    monkeypatch.setattr(cli, "load_config", lambda: dict(config))
    ws = Workspace(tmp_path, config=config, client=client)
    return ws


def test_full_lifecycle(tmp_path, client, cleanup, live_ws, capsys):
    private = client.create_gist(
        files={"a.md": "hello private"}, description=f"ws-live-private-{NONCE}"
    )
    public = client.create_gist(
        files={"b.md": "hello public"}, description=f"ws-live-public-{NONCE}", public=True
    )
    cleanup.extend([private["id"], public["id"]])

    summary = live_ws.sync()
    assert len(summary.cloned) == 2
    private_dir = conv.gist_dir_name(private.get("description"), private["id"])
    public_dir = conv.gist_dir_name(public.get("description"), public["id"])
    assert (tmp_path / private_dir / "a.md").read_text(encoding="utf-8") == "hello private"
    assert (tmp_path / public_dir / "b.md").read_text(encoding="utf-8") == "hello public"

    (tmp_path / private_dir / "a.md").write_text("updated via push", encoding="utf-8")
    results = live_ws.push(selector=private_dir)
    assert results == [(private_dir, "pushed")]
    pushed = client.get_gist(private["id"])
    assert pushed["files"]["a.md"]["content"] == "updated via push"

    client.star_gist(private["id"])
    starred_ids = {g["id"] for g in client.list_starred()}
    assert private["id"] in starred_ids
    client.unstar_gist(private["id"])

    rc = cli.main(["archive", private_dir])
    assert rc == 0
    archived = client.get_gist(private["id"])
    assert conv.is_archived(archived.get("description"))
    archived_dir = conv.gist_dir_name(archived.get("description"), private["id"])

    rc = cli.main(["unarchive", archived_dir])
    assert rc == 0
    restored = client.get_gist(private["id"])
    assert not conv.is_archived(restored.get("description"))
    restored_dir = conv.gist_dir_name(restored.get("description"), private["id"])

    rc = cli.main(["rename", restored_dir, f"ws-live-renamed-{NONCE}"])
    assert rc == 0
    renamed = client.get_gist(private["id"])
    assert renamed["description"] == f"ws-live-renamed-{NONCE}"
    renamed_dir = conv.gist_dir_name(renamed["description"], private["id"])
    assert (tmp_path / renamed_dir).exists()

    rc = cli.main(["comment", "add", renamed_dir, "live comment"])
    assert rc == 0
    comments = client.list_comments(private["id"])
    assert [c["body"] for c in comments] == ["live comment"]
    comment_id = comments[0]["id"]
    client.update_comment(private["id"], comment_id, "live comment edited")
    assert client.list_comments(private["id"])[0]["body"] == "live comment edited"
    client.delete_comment(private["id"], comment_id)
    assert client.list_comments(private["id"]) == []

    rc = cli.main(["duplicate", renamed_dir])
    assert rc == 0
    out = capsys.readouterr().out
    duplicate_line = next(line for line in out.splitlines() if line.startswith("duplicated to "))
    duplicate_dir = duplicate_line.split()[2]
    duplicates = [
        g
        for g in client.list_gists()
        if (g.get("description") or "").startswith(f"ws-live-renamed-{NONCE} (Copy)")
    ]
    assert len(duplicates) == 1
    cleanup.append(duplicates[0]["id"])
    assert (tmp_path / duplicate_dir / "a.md").exists()

    rc = cli.main(["delete", renamed_dir, "--yes"])
    assert rc == 0
    with pytest.raises(ApiError):
        client.get_gist(private["id"])
    cleanup.remove(private["id"])
    assert not (tmp_path / renamed_dir).exists()
