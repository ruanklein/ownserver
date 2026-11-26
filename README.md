# Ownserver

<p align="center">
  <img src="logo.webp" alt="Ownserver logo" width="480">
</p>

Ownserver serves a directory over HTTP and opens an ngrok tunnel by default. It uses Python's standard library for the local server and the official ngrok Python SDK for the public tunnel.

## Requirements

- [uv](https://docs.astral.sh/uv/) installed.
- Python 3.15 or newer. `uv` can select or install a compatible Python version.
- An ngrok account and authtoken when using the default tunnel mode.

Set the token in your Nushell session before starting Ownserver:

```nu
$env.NGROK_AUTHTOKEN = "YOUR_NGROK_AUTHTOKEN"
```

The token is read from the environment and is never accepted as a command-line argument.

## Run from the project

Run these commands from the project directory. `uv run` synchronizes the project environment before starting the command.

```nu
uv run ownserver -p 8000
uv run ownserver -p 8000 ./public home.html
uv run ownserver -p 8000 --watch ./public
```

By default, Ownserver starts both the local HTTP server and an ngrok tunnel. It prints the local address and the public ngrok URL. The server listens on `127.0.0.1` unless `--host` is supplied. Use `--domain` with a domain reserved in your ngrok account:

```nu
uv run ownserver -p 8000 --domain my-site.ngrok.app ./public
```

Use `--no-ngrok` to serve locally without requiring an ngrok token:

```nu
uv run ownserver -p 8000 --no-ngrok ./public
```

The optional positional arguments are the directory to serve (default: current directory) and the file served at `/` (default: `index.html`). `--watch` monitors file and directory changes and reloads open HTML pages. Run `uv run ownserver --help` to see all options.

## JSON output

Use `--json` to write machine-readable status and error records to standard output:

```nu
uv run ownserver -p 8000 --json
```

Ownserver writes one compact JSON object per line. The first record reports `server`, `watch`, `directory`, `host`, `port`, and `url`; `url` is `null` when `--no-ngrok` is used. Startup or fatal runtime errors use `server: "error"` and an `error` message. HTTP error responses include an `error`, their status, method, and request path while `server` remains `"ready"`. Human-readable startup, watcher, and access logs remain on standard error.

Example status record:

```json
{"server":"ready","watch":true,"directory":"/path/to/site","host":"http://127.0.0.1","port":8000,"url":"https://example.ngrok.app"}
```

Example HTTP error record:

```json
{"server":"ready","error":"HTTP 404 response","status":404,"method":"GET","path":"/missing"}
```

## Install the command for your user

From the project directory, install the command into uv's user tool environment:

```nu
uv tool install .
```

To locate the executable directory:

```nu
uv tool dir --bin
```

If `ownserver` is not found, add that directory to Nushell's `PATH`. To apply the change for the current session, run:

```nu
$env.PATH = ($env.PATH | prepend (uv tool dir --bin | str trim))
```

For a persistent change, add the same line to the Nushell environment file shown by `$nu.env-path`, then restart Nushell. Once the executable directory is on `PATH`, use the command directly:

```nu
ownserver -p 8000
ownserver -p 8000 --no-ngrok
```

Uninstall the user-level command with:

```nu
uv tool uninstall ownserver
```
