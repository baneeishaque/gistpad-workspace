"""Command-line interface for gistpad-workspace."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from gistpad_workspace import __version__, git
from gistpad_workspace import conventions as conv
from gistpad_workspace.api import GitHubClient
from gistpad_workspace.config import load_config, workspace_root
from gistpad_workspace.errors import GistpadError
from gistpad_workspace.workspace import SyncSummary, Workspace


def _add_selector(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("gist", nargs="?", help="gist id, id prefix, dir, or description")
    parser.add_argument("--path", help="resolve the owning gist from a file path")


def _workspace(args: argparse.Namespace, need_client: bool = False) -> Workspace:
    config = load_config()
    root = getattr(args, "root", None)
    base = Path(root).expanduser() if root else workspace_root(config)
    client = GitHubClient() if need_client else None
    return Workspace(base, config=config, client=client)


def _resolve(ws: Workspace, args: argparse.Namespace) -> dict[str, Any]:
    path = getattr(args, "path", None)
    if path:
        return ws.resolve_by_path(path)
    gist = getattr(args, "gist", None)
    if gist:
        return ws.resolve(gist)
    raise GistpadError("Specify a gist or --path.")


def _prompt(label: str, default: str | None = None) -> str:
    if not sys.stdin.isatty():
        raise GistpadError(f"{label} required (no interactive terminal available)")
    suffix = f" [{default}]" if default else ""
    answer = input(f"{label}{suffix}: ").strip()
    return answer or (default or "")


def _open_in_zed(path: Path) -> None:
    zed = shutil.which("zed")
    if zed:
        subprocess.run([zed, str(path)], check=False)
    else:
        print(f"Zed CLI not found; open manually: {path}")


def _print_sync(summary: SyncSummary) -> None:
    groups = (
        ("cloned", summary.cloned),
        ("pulled", summary.pulled),
        ("renamed", [f"{old} -> {new}" for old, new in summary.renamed]),
        ("rename deferred (uncommitted changes)", summary.deferred_renames),
        ("skipped (uncommitted changes)", summary.skipped_dirty),
        ("ahead (push needed)", summary.ahead),
        ("removed remotely", summary.removed),
        ("pruned", summary.pruned),
        ("errors", summary.errors),
    )
    for label, items in groups:
        for item in items:
            print(f"{label}: {item}")
    print(f"unchanged: {summary.unchanged}")


def cmd_init(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    for action in ws.init():
        print(action)
    if args.sync:
        ws.client = GitHubClient()
        _print_sync(ws.sync())
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    ws = _workspace(args, need_client=True)
    _print_sync(ws.sync(dry_run=args.dry_run, prune=args.prune))
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    results = ws.push(selector=args.gist, push_all=args.all, message=args.message, path=args.path)
    for name, state in results:
        print(f"{name}: {state}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    rows = ws.status()
    if not rows:
        print("No gists in the manifest. Run 'gistpad-workspace sync'.")
        return 0
    width = max(len(row["dir"]) for row in rows)
    for row in rows:
        print(f"{row['dir']:<{width}}  {row['state']}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    gists = ws.manifest["gists"]
    if args.starred:
        gists = [g for g in gists if g.get("starred")]
    if args.archived:
        gists = [g for g in gists if g.get("archived")]
    if not gists:
        print("No matching gists. Run 'gistpad-workspace sync'.")
        return 0
    width = max(len(g["dir"]) for g in gists)
    for g in gists:
        flags = "".join(
            flag
            for flag, on in (
                ("S", g.get("starred")),
                ("A", g.get("archived")),
                ("P", g.get("public")),
            )
            if on
        )
        print(f"{g['dir']:<{width}}  {flags:<3} {g.get('description') or ''}")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    files: dict[str, str] = {}
    for spec in args.file or []:
        if "=" not in spec:
            raise GistpadError(f"--file expects NAME=CONTENT or NAME=@PATH, got '{spec}'")
        name, value = spec.split("=", 1)
        if value.startswith("@"):
            value = Path(value[1:]).expanduser().read_text(encoding="utf-8")
        files[name] = conv.encode_file_content(value)
    description = args.description
    if not files:
        name = _prompt("Filename", "untitled.md")
        description = description or _prompt("Description (optional)", "")
        files[name] = conv.EMPTY_FILE_SENTINEL
    ws = _workspace(args, need_client=True)
    gist = ws.client.create_gist(files=files, description=description or None, public=args.public)
    entry = ws.register_gist(gist)
    print(f"created {entry['dir']} ({conv.gist_url(gist['id'])})")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    ws = _workspace(args, need_client=True)
    entry = _resolve(ws, args)
    if not args.yes:
        label = entry.get("description") or entry["id"][:8]
        answer = _prompt(f"Delete gist '{label}'? [y/N]", "n")
        if answer.lower() not in ("y", "yes"):
            print("aborted")
            return 1
    ws.client.delete_gist(entry["id"])
    ws.trash(entry["dir"])
    ws.manifest["gists"] = [g for g in ws.manifest["gists"] if g["id"] != entry["id"]]
    ws.refresh_special_ids()
    ws.save()
    print(f"deleted {entry['dir']}")
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    ws = _workspace(args, need_client=True)
    entry = _resolve(ws, args)
    new_description = args.description
    if conv.is_archived(entry.get("description")) and not conv.is_archived(new_description):
        new_description = conv.archive_description(new_description)
    ws.client.update_gist(entry["id"], new_description)
    entry["description"] = new_description
    entry["archived"] = conv.is_archived(new_description)
    warning = ws.apply_rename(entry)
    ws.refresh_special_ids()
    ws.save()
    print(f"renamed to '{new_description}' ({entry['dir']})")
    if warning:
        print(f"warning: {warning}")
    return 0


def _set_starred(ws: Workspace, entry: dict[str, Any], starred: bool) -> int:
    if starred:
        ws.client.star_gist(entry["id"])
    else:
        ws.client.unstar_gist(entry["id"])
    entry["starred"] = starred
    ws.save()
    print(f"{'starred' if starred else 'unstarred'} {entry['dir']}")
    return 0


def cmd_star(args: argparse.Namespace) -> int:
    ws = _workspace(args, need_client=True)
    entry = _resolve(ws, args)
    starred = not entry.get("starred", False) if args.toggle else True
    return _set_starred(ws, entry, starred)


def cmd_unstar(args: argparse.Namespace) -> int:
    ws = _workspace(args, need_client=True)
    entry = _resolve(ws, args)
    return _set_starred(ws, entry, False)


def _set_archived(ws: Workspace, entry: dict[str, Any], archived: bool) -> int:
    if conv.is_daily_gist(entry.get("description")):
        raise GistpadError("The daily gist cannot be archived.")
    description = entry.get("description")
    new_description = (
        conv.archive_description(description)
        if archived
        else conv.unarchive_description(description)
    )
    ws.client.update_gist(entry["id"], new_description)
    entry["description"] = new_description
    entry["archived"] = archived
    warning = ws.apply_rename(entry)
    ws.refresh_special_ids()
    ws.save()
    print(f"{'archived' if archived else 'unarchived'} {entry['dir']}")
    if warning:
        print(f"warning: {warning}")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    ws = _workspace(args, need_client=True)
    entry = _resolve(ws, args)
    archived = not entry.get("archived", False) if args.toggle else True
    return _set_archived(ws, entry, archived)


def cmd_unarchive(args: argparse.Namespace) -> int:
    ws = _workspace(args, need_client=True)
    entry = _resolve(ws, args)
    return _set_archived(ws, entry, False)


def cmd_duplicate(args: argparse.Namespace) -> int:
    ws = _workspace(args, need_client=True)
    entry = _resolve(ws, args)
    source = ws.client.get_gist(entry["id"])
    files = {
        name: conv.encode_file_content(file.get("content") or "")
        for name, file in (source.get("files") or {}).items()
    }
    gist = ws.client.create_gist(
        files=files,
        description=conv.duplicate_description(source.get("description")),
        public=bool(source.get("public")),
    )
    new_entry = ws.register_gist(gist)
    print(f"duplicated to {new_entry['dir']} ({conv.gist_url(gist['id'])})")
    return 0


def cmd_comment(args: argparse.Namespace) -> int:
    ws = _workspace(args, need_client=True)
    entry = _resolve(ws, args)
    if args.action == "list":
        comments = ws.client.list_comments(entry["id"])
        if not comments:
            print("no comments")
            return 0
        for comment in comments:
            first_line = (comment.get("body") or "").splitlines()
            preview = first_line[0] if first_line else ""
            print(
                f"{comment['id']}  {comment['user']['login']}  {comment['created_at']}  {preview}"
            )
        return 0
    if args.action == "add":
        body = args.body or _prompt("Comment")
        if not body:
            raise GistpadError("Comment body is empty.")
        comment = ws.client.create_comment(entry["id"], body)
        print(f"comment {comment['id']} created")
        return 0
    if args.action == "edit":
        body = args.body or _prompt("Comment")
        if not body:
            raise GistpadError("Comment body is empty.")
        ws.client.update_comment(entry["id"], args.comment_id, body)
        print(f"comment {args.comment_id} updated")
        return 0
    ws.client.delete_comment(entry["id"], args.comment_id)
    print(f"comment {args.comment_id} deleted")
    return 0


def _ensure_daily_gist(ws: Workspace, date_iso: str) -> dict[str, Any]:
    daily_id = ws.manifest.get("daily_gist_id")
    entry = next((g for g in ws.manifest["gists"] if g["id"] == daily_id), None)
    if entry is None:
        entry = next(
            (g for g in ws.manifest["gists"] if conv.is_daily_gist(g.get("description"))),
            None,
        )
    if entry is None:
        match = next(
            (g for g in ws.client.list_gists() if conv.is_daily_gist(g.get("description"))),
            None,
        )
        if match is not None:
            entry = ws.register_gist(match)
        else:
            gist = ws.client.create_gist(
                files={conv.daily_file_name(date_iso): conv.render_daily_content(None, date_iso)},
                description=conv.DAILY_GIST_DESCRIPTION,
            )
            entry = ws.register_gist(gist)
    repo = ws.root / entry["dir"]
    if not repo.exists():
        git.clone(entry["id"], repo)
    return entry


def cmd_daily(args: argparse.Namespace) -> int:
    ws = _workspace(args, need_client=True)
    date_iso = args.date or conv.today_iso()
    file_name = conv.daily_file_name(date_iso)
    entry = _ensure_daily_gist(ws, date_iso)
    repo = ws.root / entry["dir"]
    file_path = repo / file_name
    if not file_path.exists():
        template_path = repo / "template.md"
        if args.template and not template_path.exists():
            raise GistpadError(f"No template.md found in {entry['dir']}.")
        template = template_path.read_text(encoding="utf-8") if template_path.exists() else None
        content = conv.render_daily_content(template, date_iso)
        ws.client.update_gist_files(entry["id"], {file_name: content})
        if not git.is_dirty(repo):
            git.fetch(repo)
            git.pull_ff_only(repo)
        if not file_path.exists():
            file_path.write_text(content, encoding="utf-8")
    print(str(file_path))
    if args.open:
        _open_in_zed(file_path)
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    entry = _resolve(ws, args)
    path = ws.root / entry["dir"]
    if args.file:
        path = path / args.file
    if not path.exists():
        raise GistpadError(f"{path} does not exist. Run 'gistpad-workspace sync'.")
    _open_in_zed(path)
    return 0


def cmd_url(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    entry = _resolve(ws, args)
    print(conv.gist_url(entry["id"]))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    failures = 0
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        print("ok: GITHUB_TOKEN is set")
    else:
        failures += 1
        print("fail: GITHUB_TOKEN is not set (export a token with the 'gist' scope)")

    git_path = shutil.which("git")
    if git_path:
        version = subprocess.run([git_path, "--version"], capture_output=True, text=True)
        print(f"ok: {version.stdout.strip()}")
    else:
        failures += 1
        print("fail: git not found")

    zed_path = shutil.which("zed")
    if zed_path:
        print(f"ok: zed CLI at {zed_path}")
    else:
        print("warn: zed CLI not found; 'open' and 'daily --open' will print paths")

    if token:
        try:
            user = GitHubClient().get_user()
            print(f"ok: GitHub API reachable as {user.get('login')}")
        except GistpadError as exc:
            failures += 1
            print(f"fail: {exc}")

    config = load_config()
    root = workspace_root(config)
    if root.exists():
        print(f"ok: workspace root {root}")
    else:
        print(f"warn: workspace root {root} does not exist yet (run 'gistpad-workspace init')")
    ws = Workspace(root, config=config)
    print(f"ok: manifest lists {len(ws.manifest['gists'])} gists")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gistpad-workspace",
        description="Local-first GitHub gist workspace for Zed.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create root, config, manifest, README, .zed/tasks.json")
    p.add_argument("--root", help="workspace root (default: config workspace_root)")
    p.add_argument("--sync", action="store_true", help="run a first sync after init")
    p.set_defaults(handler=cmd_init)

    p = sub.add_parser("sync", help="clone new gists and pull remote updates")
    p.add_argument("--dry-run", action="store_true", help="report planned actions only")
    p.add_argument("--prune", action="store_true", help="trash dirs of gists removed remotely")
    p.set_defaults(handler=cmd_sync)

    p = sub.add_parser("push", help="commit local changes and push")
    _add_selector(p)
    p.add_argument("--all", action="store_true", help="push every gist")
    p.add_argument("--message", help="commit message for local changes")
    p.set_defaults(handler=cmd_push)

    p = sub.add_parser("status", help="per-gist clean/dirty/ahead/behind table")
    p.set_defaults(handler=cmd_status)

    p = sub.add_parser("list", help="list gists known to the manifest")
    p.add_argument("--starred", action="store_true")
    p.add_argument("--archived", action="store_true")
    p.set_defaults(handler=cmd_list)

    p = sub.add_parser("create", help="create a gist and clone it")
    p.add_argument("--description")
    p.add_argument("--public", action="store_true")
    p.add_argument("--file", action="append", metavar="NAME=CONTENT|NAME=@PATH")
    p.set_defaults(handler=cmd_create)

    p = sub.add_parser("delete", help="delete a gist and trash its folder")
    _add_selector(p)
    p.add_argument("--yes", action="store_true", help="skip confirmation")
    p.set_defaults(handler=cmd_delete)

    p = sub.add_parser("rename", help="update a gist description and rename its folder")
    p.add_argument("gist")
    p.add_argument("description")
    p.set_defaults(handler=cmd_rename)

    p = sub.add_parser("star", help="star a gist")
    _add_selector(p)
    p.add_argument("--toggle", action="store_true", help="flip the current star state")
    p.set_defaults(handler=cmd_star)

    p = sub.add_parser("unstar", help="unstar a gist")
    _add_selector(p)
    p.set_defaults(handler=cmd_unstar)

    p = sub.add_parser("archive", help="append ' [Archived]' to the description")
    _add_selector(p)
    p.add_argument("--toggle", action="store_true", help="flip the archived state")
    p.set_defaults(handler=cmd_archive)

    p = sub.add_parser("unarchive", help="remove the ' [Archived]' suffix")
    _add_selector(p)
    p.set_defaults(handler=cmd_unarchive)

    p = sub.add_parser("duplicate", help="copy a gist with a ' (Copy)' description")
    _add_selector(p)
    p.set_defaults(handler=cmd_duplicate)

    p = sub.add_parser("comment", help="manage gist comments")
    csub = p.add_subparsers(dest="action", required=True)
    q = csub.add_parser("list", help="list comments")
    _add_selector(q)
    q.set_defaults(handler=cmd_comment)
    q = csub.add_parser("add", help="add a comment")
    _add_selector(q)
    q.add_argument("body", nargs="?")
    q.set_defaults(handler=cmd_comment)
    q = csub.add_parser("edit", help="edit a comment")
    _add_selector(q)
    q.add_argument("comment_id")
    q.add_argument("body", nargs="?")
    q.set_defaults(handler=cmd_comment)
    q = csub.add_parser("delete", help="delete a comment")
    _add_selector(q)
    q.add_argument("comment_id")
    q.set_defaults(handler=cmd_comment)

    p = sub.add_parser("daily", help="ensure the daily note exists")
    p.add_argument("--date", help="ISO date (default: today)")
    p.add_argument("--open", action="store_true", help="open the note in Zed")
    p.add_argument("--template", action="store_true", help="require template.md in the daily gist")
    p.set_defaults(handler=cmd_daily)

    p = sub.add_parser("open", help="open a gist (or one file) in Zed")
    _add_selector(p)
    p.add_argument("file", nargs="?")
    p.set_defaults(handler=cmd_open)

    p = sub.add_parser("url", help="print a gist's URL")
    _add_selector(p)
    p.set_defaults(handler=cmd_url)

    p = sub.add_parser("doctor", help="check token, git, zed CLI, workspace, manifest")
    p.set_defaults(handler=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except GistpadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
