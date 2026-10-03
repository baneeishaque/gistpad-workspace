"""Minimal GitHub REST client (stdlib-only) for gists and comments."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from gistpad_workspace import __version__
from gistpad_workspace.errors import ApiError, AuthError

API_ROOT = "https://api.github.com"
DEFAULT_TIMEOUT = 30
PER_PAGE = 100


def _describe_http_error(exc: urllib.error.HTTPError) -> str:
    detail = ""
    try:
        body = json.loads(exc.read().decode("utf-8"))
        detail = body.get("message", "")
    except Exception:
        detail = ""
    if exc.code == 401:
        guidance = "Check that GITHUB_TOKEN is valid and has the 'gist' scope."
        prefix = f"GitHub rejected the token (401). {detail.rstrip('.')}".rstrip()
        return f"{prefix}. {guidance}"
    if exc.code == 403:
        fallback = "The token may lack the 'gist' scope, or a rate limit was hit."
        return f"Access forbidden (403). {detail or fallback}"
    if exc.code == 404:
        fallback = "The gist or comment does not exist, or the token cannot see it."
        return f"Not found (404). {detail or fallback}"
    return f"GitHub API error {exc.code}: {detail or exc.reason}"


class GitHubClient:
    """Thin wrapper over the GitHub REST surface used by gistpad-workspace."""

    def __init__(self, token: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> None:
        resolved = token or os.environ.get("GITHUB_TOKEN")
        if not resolved:
            raise AuthError(
                "No GitHub token found. Set GITHUB_TOKEN, or write the token to "
                "<workspace>/.gistpad-workspace/token (one token per workspace, so "
                "multiple GitHub accounts stay separate). Create one at "
                "https://github.com/settings/tokens with the 'gist' scope."
            )
        self._token = resolved
        self._timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        url = API_ROOT + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=body, method=method)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("User-Agent", f"gistpad-workspace/{__version__}")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ApiError(exc.code, _describe_http_error(exc), url=url) from exc
        except urllib.error.URLError as exc:
            raise ApiError(None, f"Network error contacting {url}: {exc.reason}", url=url) from exc
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def _paginate(self, path: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self._request("GET", path, params={"per_page": PER_PAGE, "page": page})
            results.extend(batch)
            if len(batch) < PER_PAGE:
                return results
            page += 1

    def list_gists(self) -> list[dict[str, Any]]:
        return self._paginate("/gists")

    def list_starred(self) -> list[dict[str, Any]]:
        return self._paginate("/gists/starred")

    def get_user(self) -> dict[str, Any]:
        return self._request("GET", "/user")

    def get_gist(self, gist_id: str) -> dict[str, Any]:
        return self._request("GET", f"/gists/{gist_id}")

    def create_gist(
        self,
        files: dict[str, str],
        description: str | None = None,
        public: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "files": {name: {"content": content} for name, content in files.items()},
            "public": public,
        }
        if description is not None:
            payload["description"] = description
        return self._request("POST", "/gists", payload=payload)

    def update_gist(self, gist_id: str, description: str) -> dict[str, Any]:
        return self._request("PATCH", f"/gists/{gist_id}", payload={"description": description})

    def update_gist_files(self, gist_id: str, files: dict[str, str | None]) -> dict[str, Any]:
        payload = {
            "files": {
                name: (None if content is None else {"content": content})
                for name, content in files.items()
            }
        }
        return self._request("PATCH", f"/gists/{gist_id}", payload=payload)

    def delete_gist(self, gist_id: str) -> None:
        self._request("DELETE", f"/gists/{gist_id}")

    def star_gist(self, gist_id: str) -> None:
        self._request("PUT", f"/gists/{gist_id}/star")

    def unstar_gist(self, gist_id: str) -> None:
        self._request("DELETE", f"/gists/{gist_id}/star")

    def list_comments(self, gist_id: str) -> list[dict[str, Any]]:
        return self._paginate(f"/gists/{gist_id}/comments")

    def create_comment(self, gist_id: str, body: str) -> dict[str, Any]:
        return self._request("POST", f"/gists/{gist_id}/comments", payload={"body": body})

    def update_comment(self, gist_id: str, comment_id: str, body: str) -> dict[str, Any]:
        return self._request(
            "PATCH", f"/gists/{gist_id}/comments/{comment_id}", payload={"body": body}
        )

    def delete_comment(self, gist_id: str, comment_id: str) -> None:
        self._request("DELETE", f"/gists/{gist_id}/comments/{comment_id}")
