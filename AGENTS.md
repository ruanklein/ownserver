# Ownserver Agent Guide

## Project

Ownserver is a Python command-line tool that serves a local directory over HTTP. It starts an ngrok tunnel by default and can optionally watch the served tree and reload open HTML pages when files or directories change.

- Package and command: `ownserver`
- Source layout: `src/ownserver/`
- Minimum Python version: 3.15
- Project and environment manager: `uv`
- Runtime dependency: the official `ngrok` Python SDK. The local HTTP server and file watcher use the Python standard library.
- User documentation: `README.md` (English)

Keep source code, comments, CLI help, and user-facing messages in English. In the README, use shared `console` examples for commands that work in both Bash and PowerShell; show shell-specific variants only for environment variable setup.

## Run and build

Run project commands through `uv` from the repository root:

```console
uv sync --locked
uv run ownserver --help
uv run ownserver -p 8000 --no-ngrok ./public
uv lock --check
uv build
```

Normal use requires `NGROK_AUTHTOKEN` in the environment because ngrok is enabled by default. `--no-ngrok` runs only the local server. Do not put the token in command-line arguments, source files, logs, or examples.

## CLI behavior

The command shape is:

```text
ownserver -p PORT [DIRECTORY] [DEFAULT_INDEX]
```

- `-p` / `--port` is required and must be in the TCP port range.
- `DIRECTORY` defaults to the current directory.
- `DEFAULT_INDEX` defaults to `index.html` and is served at `/`.
- `--watch` enables recursive polling and browser live reload.
- `--host` defaults to `127.0.0.1`.
- ngrok starts by default. `--no-ngrok` disables it; `--domain` selects a reserved ngrok domain and cannot be combined with `--no-ngrok`.
- `--json` writes compact JSON Lines status and error records to stdout. Keep human-readable logs on stderr in this mode. HTTP error records describe request failures while the server remains ready.
- Help and CLI messages are English. Terminal colors are conditional on TTY output and `NO_COLOR`.

Resolve and validate served paths before starting services. Keep requests confined to the configured document root, and do not expose the `.git` directory. Preserve cleanup of the HTTP server, watcher, and ngrok listener on normal shutdown and startup/runtime errors.

## Source map

- `__main__.py` — `python -m ownserver` entry point.
- `app.py` — parses arguments, validates paths, starts the HTTP server, optional watcher and ngrok tunnel, emits startup status, and coordinates shutdown and errors.
- `cli.py` — argument definitions, port validation, colored help, and JSON-formatted argument errors.
- `http_server.py` — threaded HTTP serving, root index handling, path checks, request logs, JSON HTTP error events, and the injected browser reload script.
- `watcher.py` — standard-library polling watcher. It snapshots the served tree, skips `.git` and symlinked directories, and increments a version used by the browser reload endpoint.
- `ngrok_tunnel.py` — token validation and lifecycle wrapper around the official ngrok SDK. Keep the token redacted from SDK error details.
- `console.py` — terminal color handling, human-readable logs, and thread-safe JSON Lines output.
- `__init__.py` — package version.

Keep module ownership focused: CLI parsing belongs in `cli.py`, service startup and cleanup in `app.py`, HTTP behavior in `http_server.py`, and ngrok SDK calls in `ngrok_tunnel.py`.

## Changes and verification

- Update `uv.lock` when dependency metadata in `pyproject.toml` changes; keep locked installs working with `uv sync --locked`.
- Build distributable artifacts with `uv build` after packaging changes.
- For behavior changes, run a local smoke check with `--no-ngrok` unless the change requires ngrok specifically. Keep ngrok verification isolated from a user's real account when possible.
- There is currently no test runner declared in `pyproject.toml`; do not assume additional development dependencies are installed.
- Do not commit, push, or publish changes unless the user requests it.
