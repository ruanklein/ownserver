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
_OUTPUT_LOCK = threading.RLock()
_ACTIVE_STATUS = None


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
    write_line("[{}] {}".format(level, message), color, stream)


def write_line(message, color=None, stream=sys.stdout):
    """Write one line while keeping an active status line intact."""
    with _OUTPUT_LOCK:
        status = _ACTIVE_STATUS
        redraw_status = status is not None and status.shares_terminal(stream)
        if redraw_status:
            status._clear_locked()

        text = paint(message, color, stream) if color is not None else str(message)
        print(text, file=stream, flush=True)

        if redraw_status and _ACTIVE_STATUS is status:
            status._draw_locked()


class StatusLine:
    """Animate a compact live status in one interactive terminal line."""

    FRAMES = ("·", "•", "●", "•")

    def __init__(self, address, stream=sys.stdout, interval=0.25):
        self.address = address
        self.stream = stream
        self.interval = interval
        self._enabled = False
        self._frame_index = 0
        self._stop_event = threading.Event()
        self._thread = None

    def shares_terminal(self, stream):
        """Return whether a log stream should temporarily hide this line."""
        if stream is self.stream:
            return True
        try:
            return stream.isatty() and self.stream.isatty()
        except (AttributeError, OSError):
            return False

    def start(self):
        """Start animation only when output is a color-enabled terminal."""
        global _ACTIVE_STATUS

        if not self.stream.isatty() or "NO_COLOR" in os.environ:
            return

        with _OUTPUT_LOCK:
            self._enabled = True
            _ACTIVE_STATUS = self
            self._draw_locked()
            self._thread = threading.Thread(
                target=self._animate,
                name="ownserver-status-line",
                daemon=True,
            )
            self._thread.start()

    def _draw_locked(self):
        frame = self.FRAMES[self._frame_index]
        frame = paint(frame, "green", self.stream)
        self.stream.write("\r\033[K{} LIVE  {}".format(frame, self.address))
        self.stream.flush()

    def _clear_locked(self):
        self.stream.write("\r\033[K")
        self.stream.flush()

    def _animate(self):
        while not self._stop_event.wait(self.interval):
            with _OUTPUT_LOCK:
                if _ACTIVE_STATUS is not self:
                    return
                self._frame_index = (self._frame_index + 1) % len(self.FRAMES)
                self._draw_locked()

    def stop(self):
        """Stop animation and clear its terminal line."""
        global _ACTIVE_STATUS

        if not self._enabled:
            return

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()

        with _OUTPUT_LOCK:
            if _ACTIVE_STATUS is self:
                self._clear_locked()
                _ACTIVE_STATUS = None
            self._enabled = False


def emit_json(payload, stream=sys.stdout):
    """Write one compact JSON record without interleaving concurrent events."""
    record = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with _JSON_LOCK:
        stream.write(record + "\n")
        stream.flush()
