# gistpad-workspace

Local-first GitHub gist workspace for [Zed](https://zed.dev): sync every gist as its own git clone
inside a single workspace folder, managed by Zed's multi-repository Git panel, with every operation
available as a Zed task.

- **No custom UI** — Zed's native explorer, editor, preview, and Git panel do the work
- **No AI** — pure GitHub REST + git
- **No daemon** — a CLI you run from the terminal or from Zed tasks
- **Zero runtime dependencies** — Python standard library only

## Why

Zed extensions cannot add UI panels (the extension API exposes only languages, themes, icon themes,
snippets, debuggers, and MCP servers). This tool instead makes gists first-class in a Zed
*workspace*: when a project is not itself a repository, repositories directly inside the project
root are all active immediately — so a folder of gist clones behaves like a multi-repo project.

## Requirements

- Python >= 3.9 (macOS system Python is fine)
- `git` on `PATH`
- A GitHub token with the `gist` scope, exported as `GITHUB_TOKEN`
- Optional: the `zed` CLI on `PATH` (used by `gistpad-workspace open`)

## Install

Recommended — as an isolated pipx tool via [mise](https://mise.jdx.dev):

```sh
mise use -g 'pipx:git+https://github.com/baneeishaque/gistpad-workspace.git@latest'
```

Or with pipx directly:

```sh
pipx install git+https://github.com/baneeishaque/gistpad-workspace.git
```

## Quickstart

```sh
export GITHUB_TOKEN=ghp_...      # add to your shell profile
gistpad-workspace init           # creates ~/Gists, config, manifest, and .zed/tasks.json
gistpad-workspace sync           # clones all your gists into the workspace
zed ~/Gists                      # open the workspace
```

Edit files in Zed, then push from the Git panel or with `gistpad-workspace push`.

## Commands

| Command | Description |
| --- | --- |
| `init` | Create the workspace root, config, manifest, README, and Zed tasks |
| `sync` | Clone new gists, pull updates, auto-rename changed descriptions |
| `push` | Commit and push local changes (`--all`, or `<gist>` / `--path`) |
| `status` | Per-gist clean/dirty/ahead/behind table |
| `list` | List gists (`--starred`, `--archived`) |
| `create` / `delete` / `rename` | Gist lifecycle |
| `star` / `unstar` / `archive` / `unarchive` | Flags and description-suffix archive |
| `comment list/add/edit/delete` | Gist comments |
| `daily` | Open (or create) today's daily note |
| `duplicate` | Copy a gist with a `" (Copy)"` description suffix |
| `url` | Print the gist URL |
| `open` | Open a gist in Zed |
| `doctor` | Check token, git, zed, workspace, and manifest health |

## Zed integration

`init` / `sync` generate `.zed/tasks.json` with tasks such as *Gist: Sync all* and *Gist: Open
today's note*, plus file-aware tasks (*Gist: Push current gist*) that use Zed's `$ZED_FILE`
variable. Bind them to keys via `task::Spawn` in your keymap:

```json
{
  "bindings": {
    "cmd-shift-g": ["task::Spawn", { "task_name": "Gist: Open today's note" }]
  }
}
```

## Conventions

Interoperable with [gistpad-mcp](https://www.npmjs.com/package/gistpad-mcp) and VS Code Gistpad:

- Archive = description suffix `" [Archived]"`
- Daily notes = gist described `"📆 Daily notes"`, files `YYYY-MM-DD.md`, optional `template.md`
  containing `{{date}}`
- Prompts = gist described `"💬 Prompts"`
- Duplicate = description suffix `" (Copy)"`
- Directory naming = kebab-case description slug + `--` + first 8 characters of the gist id

## Configuration

`~/.config/gistpad-workspace/config.json`:

```json
{
  "workspace_root": "~/Gists",
  "auto_rename": true,
  "auto_prune": false
}
```

## Development

```sh
/usr/bin/python3 bin/gistpad-workspace --version   # run straight from the source tree
ruff check . && ruff format --check .
pytest
```

The live integration suite is opt-in and mutates real data (it creates scratch gists and deletes
them again during teardown):

```sh
GITHUB_TOKEN=... pytest --run-live
```

## License

MIT — see [LICENSE](LICENSE).
