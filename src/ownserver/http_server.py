"""Static HTTP server and live-reload response handling."""

import functools
import http.server
import os
import re
import socket
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .console import emit_json, paint


RELOAD_ENDPOINT = "/__ownserver_live_reload"
RELOAD_SCRIPT_TEMPLATE = (
    "<script>(function(){"
    "let version=__VERSION__;"
    "async function poll(){"
    "try{"
    "const response=await fetch('__ENDPOINT__',{cache:'no-store'});"
    "if(!response.ok)throw new Error('Reload status request failed');"
    "const nextVersion=await response.text();"
    "if(nextVersion!==version){location.reload();return;}"
    "}catch(error){}"
    "setTimeout(poll,500);"
    "}"
    "poll();"
    "})();</script>"
)


class StaticRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve files safely from a configured root, with optional live reload."""

    def __init__(
        self,
        *args,
        directory=None,
        default_index="index.html",
        watcher=None,
        json_mode=False,
        **kwargs
    ):
        self.root = Path(directory).resolve()
        self.default_index = Path(default_index)
        self.watcher = watcher
        self.json_mode = json_mode
        super().__init__(*args, directory=str(self.root), **kwargs)

    def translate_path(self, path):
        requested_path = unquote(urlsplit(path).path)
        if requested_path == "/":
            return str(self.root / self.default_index)
        return super().translate_path(path)

    def _is_allowed_path(self, request_path):
        translated_path = Path(self.translate_path(request_path))
        try:
            resolved_path = translated_path.resolve(strict=False)
            relative_path = resolved_path.relative_to(self.root)
        except (OSError, RuntimeError, ValueError):
            return False
        if urlsplit(request_path).path == "/" and resolved_path.is_dir():
            return False
        return ".git" not in relative_path.parts

    def _is_reload_request(self):
        return urlsplit(self.path).path == RELOAD_ENDPOINT

    def _send_reload_version(self, include_body=True):
        body = str(self.watcher.version).encode("ascii")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def _reload_script(self, version):
        return (
            RELOAD_SCRIPT_TEMPLATE.replace("__VERSION__", str(version))
            .replace("__ENDPOINT__", RELOAD_ENDPOINT)
            .encode("ascii")
        )

    def _serve_html_with_reload(self):
        translated_path = Path(self.translate_path(self.path))
        if translated_path.is_dir() or self.guess_type(str(translated_path)) != "text/html":
            return False

        initial_version = self.watcher.version
        try:
            with translated_path.open("rb") as source:
                file_stat = os.fstat(source.fileno())
                content = source.read()
        except OSError:
            self.send_error(404, "File not found")
            return True

        script = self._reload_script(initial_version)
        body_pattern = re.compile(br"</body\s*>", re.IGNORECASE)
        html_pattern = re.compile(br"</html\s*>", re.IGNORECASE)
        if body_pattern.search(content):
            content = body_pattern.sub(script + b"</body>", content, count=1)
        elif html_pattern.search(content):
            content = html_pattern.sub(script + b"</html>", content, count=1)
        else:
            content += script

        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(translated_path)))
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Last-Modified", self.date_time_string(file_stat.st_mtime))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)
        return True

    def do_GET(self):
        if self.watcher is not None and self._is_reload_request():
            self._send_reload_version()
            return
        if not self._is_allowed_path(self.path):
            self.send_error(404, "File not found")
            return
        if self.watcher is not None and self._serve_html_with_reload():
            return
        super().do_GET()

    def do_HEAD(self):
        if self.watcher is not None and self._is_reload_request():
            self._send_reload_version(include_body=False)
            return
        if not self._is_allowed_path(self.path):
            self.send_error(404, "File not found")
            return
        super().do_HEAD()

    def log_message(self, format_string, *args):
        message = format_string % args
        status_match = re.search(r'"\s+(\d{3})\s', message)
        status = int(status_match.group(1)) if status_match else 0
        if self.json_mode and status >= 400:
            emit_json(
                {
                    "server": "ready",
                    "error": "HTTP {} response".format(status),
                    "status": status,
                    "method": self.command or "",
                    "path": urlsplit(self.path).path,
                }
            )
        if status >= 500:
            color = "red"
        elif status >= 400:
            color = "yellow"
        else:
            color = "cyan"
        print(
            paint("{} - {}".format(self.address_string(), message), color, sys.stderr),
            file=sys.stderr,
            flush=True,
        )


class IPv6ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    """Threaded HTTP server configured for IPv6 addresses."""

    address_family = socket.AF_INET6


def create_server(host, port, root, default_index, watcher, json_mode=False):
    """Create a threaded HTTP server for the configured directory."""
    handler = functools.partial(
        StaticRequestHandler,
        directory=str(root),
        default_index=str(default_index),
        watcher=watcher,
        json_mode=json_mode,
    )
    server_class = (
        IPv6ThreadingHTTPServer if ":" in host else http.server.ThreadingHTTPServer
    )
    return server_class((host, port), handler)
