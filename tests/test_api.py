"""Tests for the GitHub REST client."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pytest

from gistpad_workspace.api import GitHubClient
from gistpad_workspace.errors import ApiError, AuthError


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


def install_fake_urlopen(monkeypatch: pytest.MonkeyPatch, responses: list[Any]) -> list[Any]:
    calls: list[Any] = []

    def fake_urlopen(request: Any, timeout: int | None = None) -> FakeResponse:
        calls.append(request)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return FakeResponse(result)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def test_missing_token_raises_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(AuthError):
        GitHubClient()


def test_list_gists_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    page_one = [{"id": f"g{i}"} for i in range(100)]
    page_two = [{"id": "g100"}, {"id": "g101"}]
    responses = [json.dumps(page_one).encode(), json.dumps(page_two).encode()]
    calls = install_fake_urlopen(monkeypatch, responses)

    gists = GitHubClient(token="t").list_gists()

    assert len(gists) == 102
    assert len(calls) == 2
    query_one = urllib.parse.parse_qs(urllib.parse.urlparse(calls[0].full_url).query)
    query_two = urllib.parse.parse_qs(urllib.parse.urlparse(calls[1].full_url).query)
    assert query_one["page"] == ["1"]
    assert query_two["page"] == ["2"]
    assert query_one["per_page"] == ["100"]


def test_create_gist_sends_payload_and_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [json.dumps({"id": "abc"}).encode()]
    calls = install_fake_urlopen(monkeypatch, responses)

    created = GitHubClient(token="secret").create_gist(
        files={"notes.md": "hello"}, description="My notes", public=True
    )

    assert created == {"id": "abc"}
    request = calls[0]
    assert request.method == "POST"
    assert request.get_header("Authorization") == "Bearer secret"
    body = json.loads(request.data.decode("utf-8"))
    assert body["public"] is True
    assert body["description"] == "My notes"
    assert body["files"] == {"notes.md": {"content": "hello"}}


def test_http_error_maps_to_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    error = urllib.error.HTTPError(
        url="https://api.github.com/gists",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=io.BytesIO(b'{"message": "Bad credentials"}'),
    )
    install_fake_urlopen(monkeypatch, [error])

    with pytest.raises(ApiError) as excinfo:
        GitHubClient(token="bad").list_gists()

    assert excinfo.value.status == 401
    assert "GITHUB_TOKEN" in str(excinfo.value)


def test_delete_gist_returns_none_on_empty_body(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_fake_urlopen(monkeypatch, [b""])

    assert GitHubClient(token="t").delete_gist("abc") is None
    assert calls[0].method == "DELETE"


def test_star_and_unstar(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_fake_urlopen(monkeypatch, [b"", b""])

    client = GitHubClient(token="t")
    client.star_gist("abc")
    client.unstar_gist("abc")

    assert calls[0].method == "PUT"
    assert calls[1].method == "DELETE"
    assert calls[0].full_url.endswith("/gists/abc/star")


def test_create_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_fake_urlopen(monkeypatch, [json.dumps({"id": 1}).encode()])

    GitHubClient(token="t").create_comment("abc", "hello")

    assert calls[0].full_url.endswith("/gists/abc/comments")
    assert json.loads(calls[0].data.decode("utf-8")) == {"body": "hello"}
