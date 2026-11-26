"""Terminal colors and concise console logging."""

import json
import os
import sys
import threading


RESET = "\033[0m"
COLORS = {
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "bold": "\033[1m",
}
LEVEL_COLORS = {
    "ready": "green",
    "info": "cyan",
    "watch": "yellow",
    "warning": "yellow",
    "error": "red",
    "stopped": "green",
}
_JSON_LOCK = threading.Lock()


def color_enabled(stream):
    """Return whether ANSI colors should be used for this output stream."""
    return stream.isatty() and "NO_COLOR" not in os.environ


def paint(text, color, stream=sys.stdout):
    """Apply an ANSI color when output is connected to a terminal."""
    if not color_enabled(stream):
        return str(text)
    return "{}{}{}".format(COLORS[color], text, RESET)


def log(level, message, stream=sys.stdout):
    """Print one colored Ownserver log message."""
    color = LEVEL_COLORS.get(level, "cyan")
    print(paint("[{}] {}".format(level, message), color, stream), file=stream, flush=True)


def emit_json(payload, stream=sys.stdout):
    """Write one compact JSON record without interleaving concurrent events."""
    record = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with _JSON_LOCK:
        stream.write(record + "\n")
        stream.flush()
