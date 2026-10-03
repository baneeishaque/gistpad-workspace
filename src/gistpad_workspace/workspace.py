"""Workspace engine: init, sync, push, status, rename."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gistpad_workspace import conventions as conv
from gistpad_workspace import git
from gistpad_workspace.config import config_path, load_config, save_config
from gistpad_workspace.errors import GistpadError
from gistpad_workspace.manifest import (
    gists_by_id,
    load_manifest,
    manifest_path,
    save_manifest,
)
from gistpad_workspace.tasks import render_tasks, render_workspace_readme, write_if_changed


@dataclass
class SyncSummary:
    cloned: list[str] = field(default_factory=list)
    pulled: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)
    deferred_renames: list[str] = field(default_factory=list)
    skipped_dirty: list[str] = field(default_factory=list)
    ahead: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    unchanged: int = 0
    errors: list[str] = field(default_factory=list)


def entry_from_gist(gist: dict[str, Any], dir_name: str, starred: bool = False) -> dict[str, Any]:
    return {
        "id": gist["id"],
        "description": gist.get("description"),
        "dir": dir_name,
        "public": bool(gist.get("public")),
        "starred": starred,
        "archived": conv.is_archived(gist.get("description")),
        "updated_at": gist.get("updated_at"),
        "files": sorted((gist.get("files") or {}).keys()),
    }


class Workspace:
    def __init__(
        self,
        root: Path,
        config: dict[str, Any] | None = None,
        client: Any | None = None,
    ) -> None:
        self.root = Path(root).expanduser()
        self.config = config if config is not None else load_config()
        self.client = client
        self.manifest = load_manifest(self.root)

    def init(self) -> list[str]:
        actions: list[str] = []
        self.root.mkdir(parents=True, exist_ok=True)
        if not config_path().exists():
            save_config(self.config)
            actions.append(f"wrote config {config_path()}")
        if not manifest_path(self.root).exists():
            save_manifest(self.root, self.manifest)
            actions.append("created manifest")
        if write_if_changed(self.root / ".zed" / "tasks.json", render_tasks()):
            actions.append("wrote .zed/tasks.json")
        if write_if_changed(self.root / "README.md", render_workspace_readme()):
            actions.append("wrote README.md")
        return actions

    def sync(self, dry_run: bool = False, prune: bool | None = None) -> SyncSummary:
        if self.client is None:
            raise GistpadError("sync requires a GitHub client")
        do_prune = bool(self.config.get("auto_prune", False)) if prune is None else prune
        auto_rename = bool(self.config.get("auto_rename", True))
        summary = SyncSummary()

        remote = self.client.list_gists()
        starred = {gist["id"] for gist in self.client.list_starred()}
        remote_ids = {gist["id"] for gist in remote}
        previous = gists_by_id(self.manifest)

        entries = [
            self._sync_one(gist, previous.get(gist["id"]), starred, auto_rename, dry_run, summary)
            for gist in remote
        ]

        removed = [gist for gist in self.manifest["gists"] if gist["id"] not in remote_ids]
        for old in removed:
            summary.removed.append(old.get("dir", old["id"]))
            if do_prune and not dry_run:
                self.trash(old.get("dir", old["id"]))
                summary.pruned.append(old.get("dir", old["id"]))
        kept = entries if do_prune else entries + removed

        new_manifest = dict(self.manifest)
        new_manifest["gists"] = kept
        new_manifest["daily_gist_id"] = _first_id(remote, conv.is_daily_gist)
        new_manifest["prompts_gist_id"] = _first_id(remote, conv.is_prompts_gist)

        if not dry_run:
            self.manifest = new_manifest
            save_manifest(self.root, self.manifest)
            write_if_changed(self.root / ".zed" / "tasks.json", render_tasks())
            write_if_changed(self.root / "README.md", render_workspace_readme())
        return summary

    def _sync_one(
        self,
        gist: dict[str, Any],
        previous: dict[str, Any] | None,
        starred: set[str],
        auto_rename: bool,
        dry_run: bool,
        summary: SyncSummary,
    ) -> dict[str, Any]:
        gist_id = gist["id"]
        description = gist.get("description")
        desired_dir = conv.gist_dir_name(description, gist_id)
        old_dir = previous.get("dir") if previous else None
        current_dir = old_dir or desired_dir
        path = self.root / current_dir

        entry = entry_from_gist(gist, current_dir, starred=gist_id in starred)

        if not path.exists():
            summary.cloned.append(desired_dir)
            if not dry_run:
                git.clone(gist_id, self.root / desired_dir)
            entry["dir"] = desired_dir
            return entry

        if auto_rename and old_dir and desired_dir != old_dir:
            target = self.root / desired_dir
            if target.exists():
                summary.errors.append(f"{old_dir}: cannot rename to {desired_dir}; target exists")
            elif git.is_dirty(path):
                summary.deferred_renames.append(old_dir)
            else:
                if not dry_run:
                    path.rename(target)
                summary.renamed.append((old_dir, desired_dir))
                entry["dir"] = desired_dir
                path = self.root / desired_dir

        if previous is not None and gist.get("updated_at") != previous.get("updated_at"):
            if git.is_dirty(path):
                summary.skipped_dirty.append(entry["dir"])
            elif dry_run:
                summary.pulled.append(entry["dir"])
            else:
                git.fetch(path)
                ahead, behind = git.ahead_behind(path)
                if behind:
                    git.pull_ff_only(path)
                    summary.pulled.append(entry["dir"])
                elif ahead:
                    summary.ahead.append(entry["dir"])
                else:
                    summary.unchanged += 1
        else:
            summary.unchanged += 1
        return entry

    def push(
        self,
        selector: str | None = None,
        push_all: bool = False,
        message: str | None = None,
        path: str | None = None,
    ) -> list[tuple[str, str]]:
        if push_all:
            targets = list(self.manifest["gists"])
        elif path is not None:
            targets = [self.resolve_by_path(path)]
        elif selector:
            targets = [self.resolve(selector)]
        else:
            raise GistpadError("Specify a gist, --all, or --path.")

        results: list[tuple[str, str]] = []
        for entry in targets:
            repo = self.root / entry["dir"]
            if not repo.exists():
                results.append((entry["dir"], "missing"))
                continue
            if git.is_dirty(repo):
                git.commit_all(repo, message or "Update via gistpad-workspace")
            ahead, _behind = git.ahead_behind(repo)
            if not ahead:
                results.append((entry["dir"], "nothing to push"))
                continue
            try:
                git.push(repo)
            except GistpadError as exc:
                raise GistpadError(
                    f"{entry['dir']}: {exc} If the remote moved, pull/merge in Zed's Git panel "
                    "and push again."
                ) from exc
            results.append((entry["dir"], "pushed"))
        return results

    def status(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for entry in self.manifest["gists"]:
            repo = self.root / entry["dir"]
            row = {
                "dir": entry["dir"],
                "description": entry.get("description") or "",
                "state": "missing",
            }
            if repo.exists():
                if git.is_dirty(repo):
                    row["state"] = "dirty"
                else:
                    ahead, behind = git.ahead_behind(repo)
                    if ahead and behind:
                        row["state"] = f"diverged (+{ahead}/-{behind})"
                    elif ahead:
                        row["state"] = f"ahead +{ahead}"
                    elif behind:
                        row["state"] = f"behind -{behind}"
                    else:
                        row["state"] = "clean"
            rows.append(row)
        return rows

    def resolve(self, selector: str) -> dict[str, Any]:
        gists = self.manifest["gists"]
        lowered = selector.lower()
        matches = [g for g in gists if g["id"] == selector]
        if not matches and len(selector) >= 8:
            matches = [g for g in gists if g["id"].startswith(selector)]
        if not matches:
            matches = [g for g in gists if g["dir"] == selector]
        if not matches:
            matches = [g for g in gists if lowered in (g.get("description") or "").lower()]
        if not matches:
            raise GistpadError(f"No gist matches '{selector}'. Run 'gistpad-workspace list'.")
        if len(matches) > 1:
            names = ", ".join(g["dir"] for g in matches)
            raise GistpadError(f"'{selector}' is ambiguous: {names}")
        return matches[0]

    def resolve_by_path(self, file_path: str) -> dict[str, Any]:
        resolved = Path(file_path).resolve()
        try:
            relative = resolved.relative_to(self.root.resolve())
        except ValueError:
            raise GistpadError(
                f"{file_path} is not inside the workspace root {self.root}."
            ) from None
        first = relative.parts[0] if relative.parts else ""
        for entry in self.manifest["gists"]:
            if entry["dir"] == first:
                return entry
        raise GistpadError(f"No managed gist owns {file_path}. Run 'gistpad-workspace sync'.")

    def save(self) -> None:
        save_manifest(self.root, self.manifest)

    def refresh_special_ids(self) -> None:
        gists = self.manifest["gists"]
        self.manifest["daily_gist_id"] = _first_id(gists, conv.is_daily_gist)
        self.manifest["prompts_gist_id"] = _first_id(gists, conv.is_prompts_gist)

    def register_gist(self, gist: dict[str, Any], starred: bool = False) -> dict[str, Any]:
        """Upsert a freshly created/duplicated gist into the manifest, then clone it."""
        dir_name = conv.gist_dir_name(gist.get("description"), gist["id"])
        entry = entry_from_gist(gist, dir_name, starred=starred)
        self.manifest["gists"] = [g for g in self.manifest["gists"] if g["id"] != gist["id"]] + [
            entry
        ]
        self.refresh_special_ids()
        self.save()
        target = self.root / dir_name
        if not target.exists():
            git.clone(gist["id"], target)
        return entry

    def apply_rename(self, entry: dict[str, Any]) -> str | None:
        """Rename the local dir to match the entry description; returns a warning or None."""
        old_dir = entry["dir"]
        desired = conv.gist_dir_name(entry.get("description"), entry["id"])
        if desired == old_dir:
            return None
        source = self.root / old_dir
        target = self.root / desired
        if target.exists():
            return f"{old_dir}: target {desired} already exists; rename skipped"
        if source.exists() and git.is_dirty(source):
            return f"{old_dir}: uncommitted changes; rename deferred"
        if source.exists():
            source.rename(target)
        entry["dir"] = desired
        return None

    def trash(self, dir_name: str) -> None:
        source = self.root / dir_name
        if not source.exists():
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        dest = self.root / ".gistpad-workspace" / "trash" / stamp / dir_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(dest))


def _first_id(gists: list[dict[str, Any]], predicate: Any) -> str | None:
    for gist in gists:
        if predicate(gist.get("description")):
            return gist["id"]
    return None
