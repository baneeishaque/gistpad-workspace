"""Typed errors for gistpad-workspace."""

from __future__ import annotations


class GistpadError(Exception):
    """Base error for all gistpad-workspace failures."""


class AuthError(GistpadError):
    """Raised when no usable GitHub token is available."""


class ApiError(GistpadError):
    """Raised when the GitHub API returns an unexpected response."""

    def __init__(self, status: int | None, message: str, url: str | None = None) -> None:
        self.status = status
        self.message = message
        self.url = url
        super().__init__(message)
