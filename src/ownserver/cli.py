"""Command-line parsing for Ownserver."""

import argparse
import os
import re
import sys

from .console import emit_json, log, paint


class ColorArgumentParser(argparse.ArgumentParser):
    """Argument parser that colors the help screen and errors in terminals."""

    def __init__(self, *args, **kwargs):
        self.json_mode = False
        self.json_context = {}
        super().__init__(*args, **kwargs)

    def _style_help(self, text, stream):
        if not stream.isatty() or "NO_COLOR" in os.environ:
            return text

        styled_lines = []
        option_pattern = re.compile(r"(?<![\w])--?[A-Za-z][A-Za-z0-9_-]*")
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if line.startswith("usage:"):
                line = paint(line, "cyan", stream)
            elif stripped.endswith(":") and not line.startswith(" "):
                line = paint(line, "bold", stream)
            else:
                line = option_pattern.sub(
                    lambda match: paint(match.group(0), "green", stream), line
                )
            styled_lines.append(line)
        return "".join(styled_lines)

    def format_help(self):
        return self._style_help(super().format_help(), sys.stdout)

    def format_usage(self):
        return self._style_help(super().format_usage(), sys.stderr)

    def error(self, message):
        if self.json_mode:
            payload = {"server": "error"}
            payload.update(self.json_context)
            payload["error"] = message
            emit_json(payload)
            log("error", message, stream=sys.stderr)
            self.exit(2)
        self.print_usage(sys.stderr)
        self.exit(
            2,
            "{}\n".format(
                paint("{}: error: {}".format(self.prog, message), "red", sys.stderr)
            ),
        )


def parse_port(value):
    """Parse and validate a TCP port number."""
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer")
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def create_parser():
    parser = ColorArgumentParser(
        prog="ownserver",
        description="Serve static files over HTTP, optionally through ngrok.",
        epilog=(
            "Examples:\n"
            "  ownserver -p 8000\n"
            "  ownserver -p 8000 --watch ./public home.html\n"
            "  ownserver -p 8000 --no-ngrok ./public\n"
            "  ownserver -p 8000 --domain example.ngrok.app ./public"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-p",
        "--port",
        type=parse_port,
        required=True,
        metavar="PORT",
        help="TCP port to listen on (required)",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        metavar="DIRECTORY",
        help="directory to serve (default: current directory)",
    )
    parser.add_argument(
        "default_index",
        nargs="?",
        default="index.html",
        metavar="DEFAULT_INDEX",
        help="file served at the root route (default: index.html)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="watch files and automatically reload open HTML pages",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        metavar="ADDRESS",
        help="interface address to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--no-ngrok",
        action="store_true",
        help="serve locally without opening an ngrok tunnel",
    )
    parser.add_argument(
        "--domain",
        metavar="DOMAIN",
        help="reserved ngrok domain (default: automatically assigned)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="write status and runtime errors as JSON Lines to stdout",
    )
    return parser
