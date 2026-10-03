"""Git operations with transient token auth (never persisted to remotes)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from gistpad_workspace.errors import GistpadError

CREDENTIAL_HELPER = '!f() { echo username=x-access-token; echo password="$GITHUB_TOKEN"; }; f'


def auth_args() -> list[str]:
    return ["-c", "credential.helper=", "-c", f"credential.helper={CREDENTIAL_HELPER}"]


def run_git(
    args: list[str],
    cwd: Path | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = ["git", *args]
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        env=env,
    )
    if check and result.returncode != 0:
        raise GistpadError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def clone(gist_id: str, dest: Path, env: dict[str, str] | None = None) -> None:
    run_git([*auth_args(), "clone", f"https://gist.github.com/{gist_id}.git", str(dest)], env=env)


def fetch(repo: Path, env: dict[str, str] | None = None) -> None:
    run_git([*auth_args(), "fetch", "origin"], cwd=repo, env=env)


def pull_ff_only(repo: Path, env: dict[str, str] | None = None) -> None:
    run_git([*auth_args(), "pull", "--ff-only"], cwd=repo, env=env)


def is_dirty(repo: Path) -> bool:
    return bool(run_git(["status", "--porcelain"], cwd=repo).stdout.strip())


def ahead_behind(repo: Path) -> tuple[int, int]:
    """Return ``(ahead, behind)`` counts relative to the upstream branch."""
    result = run_git(
        ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"], cwd=repo, check=False
    )
    if result.returncode != 0:
        return (0, 0)
    left, right = result.stdout.split()
    return (int(right), int(left))


def commit_all(repo: Path, message: str) -> bool:
    run_git(["add", "-A"], cwd=repo)
    result = run_git(["commit", "-m", message], cwd=repo, check=False)
    return result.returncode == 0


def push(repo: Path, env: dict[str, str] | None = None) -> None:
    run_git([*auth_args(), "push"], cwd=repo, env=env)
