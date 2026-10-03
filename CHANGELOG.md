# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-10-03

### Added

- Workspace-scoped token file: `GITHUB_TOKEN` wins, otherwise the token is read from
  `<workspace>/.gistpad-workspace/token` — one token per workspace, so different workspaces can
  use different GitHub accounts; git subprocesses receive the resolved token via their
  environment.
- `doctor` reports the token source and warns when the token file is group/world-readable.

## [0.1.0] - 2026-10-03

### Added

- Project scaffold: package metadata (Python >= 3.9, zero runtime dependencies), MIT license,
  CI (ruff, pytest on 3.9 + 3.13, markdownlint), development runner, and package skeleton.
- Conventions module matching gistpad-mcp / VS Code Gistpad: kebab-slug directory naming
  (`<slug>--<id8>`), `" [Archived]"` suffix, daily/prompts descriptions, `" (Copy)"` duplicate
  suffix, empty-file sentinel (U+2064), and Python 3.9-safe GitHub timestamp parsing.
- Minimal stdlib GitHub REST client: paginated gist and star listing, gist create/update/delete,
  file updates, star/unstar, and comment CRUD, with typed, actionable HTTP errors.
- Workspace engine: `init` / `sync` (updated_at-gated pulls, clone-new, auto-rename on
  description change, dry-run, prune to `.gistpad-workspace/trash/`) / `push` (commit-if-dirty,
  inline credential helper, never persisted) / `status` / manifest and config management.
- Full CLI: `list`, `create`, `delete`, `rename`, `star`/`unstar`, `archive`/`unarchive`,
  `duplicate`, `comment list/add/edit/delete`, `daily`, `open`, `url`, and `doctor`, with
  `<gist>` selector resolution (id, prefix, dir, description) and `--path` for Zed tasks.
- Generated `.zed/tasks.json` (10 tasks, `$ZED_FILE`-aware) and a managed workspace `README.md`,
  rewritten only when content changes.
- Opt-in live integration suite (`pytest --run-live`): full scratch-gist lifecycle — create
  (public + private) → clone → edit → push → verify via API → star → archive → rename → comment
  → duplicate → delete — verified 2026-10-03 against the real API, with private-gist clone/push
  through the inline credential helper; all scratch gists cleaned up after the run.
