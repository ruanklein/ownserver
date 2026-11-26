"""Application startup and shutdown orchestration."""

import sys
from pathlib import Path

from .cli import create_parser
from .console import emit_json, log
from .http_server import create_server
from .ngrok_tunnel import NgrokTunnelError, open_tunnel, require_auth_token
from .watcher import FileWatcher


def resolve_paths(directory, default_index, parser):
    """Resolve and validate the document root and root index path."""
    try:
        root = Path(directory).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        parser.error("directory does not exist: {} ({})".format(directory, error))
    if not root.is_dir():
        parser.error("directory is not a directory: {}".format(root))

    index_path = Path(default_index).expanduser()
    if index_path.is_absolute():
        parser.error("default index must be a path relative to the served directory")
    try:
        resolved_index = (root / index_path).resolve(strict=False)
        relative_index = resolved_index.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        parser.error("default index must remain inside the served directory")
    if ".git" in relative_index.parts:
        parser.error("default index cannot be inside the .git directory")
    if resolved_index.exists() and not resolved_index.is_file():
        parser.error("default index is not a file: {}".format(index_path))
    return root, index_path


def _host_origin(host):
    if host in ("", "0.0.0.0"):
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"
    elif ":" in host and not host.startswith("["):
        host = "[{}]".format(host)
    return "http://{}".format(host)


def _local_url(host, port):
    return "{}:{}".format(_host_origin(host), port)


def _status_payload(args, directory, port, url, server_status="ready"):
    return {
        "server": server_status,
        "watch": args.watch,
        "directory": str(directory),
        "host": _host_origin(args.host),
        "port": port,
        "url": url,
    }


def _report_error(args, message, directory=None, port=None, url=None):
    if args.json:
        payload = {"server": "error"}
        if directory is not None:
            payload.update(
                {
                    "watch": args.watch,
                    "directory": str(directory),
                    "host": _host_origin(args.host),
                    "port": port if port is not None else args.port,
                    "url": url,
                }
            )
        payload["error"] = message
        emit_json(payload)
    log("error", message, stream=sys.stderr)


def main(argv=None):
    parser = create_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    parser.json_mode = "--json" in raw_args
    args = parser.parse_args(raw_args)
    parser.json_mode = args.json
    parser.json_context = {
        "watch": args.watch,
        "directory": args.directory,
        "host": _host_origin(args.host),
        "port": args.port,
        "url": None,
    }
    if args.no_ngrok and args.domain:
        parser.error("--domain cannot be used with --no-ngrok")
    root, index_path = resolve_paths(args.directory, args.default_index, parser)
    parser.json_context["directory"] = str(root)

    if not args.no_ngrok:
        try:
            require_auth_token()
        except NgrokTunnelError as error:
            _report_error(args, str(error), root, args.port)
            return 1

    watcher = FileWatcher(root) if args.watch else None
    server = None
    tunnel = None
    exit_code = 0
    try:
        server = create_server(
            args.host, args.port, root, index_path, watcher, json_mode=args.json
        )
        if watcher is not None:
            watcher.start()

        if not args.no_ngrok:
            tunnel = open_tunnel(args.port, args.domain, args.host)

        log_stream = sys.stderr if args.json else sys.stdout
        log(
            "ready",
            "Serving {} at {}".format(root, _local_url(args.host, args.port)),
            stream=log_stream,
        )
        if watcher is not None:
            log("watch", "Watching for file and directory changes.", stream=log_stream)
        if tunnel is not None:
            log("info", "Public ngrok URL: {}".format(tunnel.url), stream=log_stream)
        if args.json:
            emit_json(
                _status_payload(
                    args,
                    root,
                    server.server_address[1],
                    tunnel.url if tunnel else None,
                )
            )
        server.serve_forever()
    except KeyboardInterrupt:
        log("stopped", "Server stopped.", stream=sys.stderr if args.json else sys.stdout)
    except (NgrokTunnelError, OSError) as error:
        _report_error(
            args,
            str(error),
            root,
            server.server_address[1] if server is not None else args.port,
            tunnel.url if tunnel is not None else None,
        )
        exit_code = 1
    except Exception as error:
        _report_error(
            args,
            "Unexpected server error: {}".format(error),
            root,
            server.server_address[1] if server is not None else args.port,
            tunnel.url if tunnel is not None else None,
        )
        exit_code = 1
    finally:
        if server is not None:
            try:
                server.server_close()
            except OSError as error:
                _report_error(
                    args,
                    "Could not close the HTTP server cleanly: {}".format(error),
                    root,
                    server.server_address[1],
                    tunnel.url if tunnel is not None else None,
                )
                exit_code = 1
        if watcher is not None:
            watcher.stop()
        if tunnel is not None:
            try:
                tunnel.close()
            except Exception as error:
                _report_error(
                    args,
                    "Could not close the ngrok listener cleanly: {}".format(error),
                    root,
                    server.server_address[1] if server is not None else args.port,
                    tunnel.url,
                )
                exit_code = 1
    return exit_code
