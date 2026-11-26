"""Polling-based recursive filesystem watcher for browser live reload."""

import os
import sys
import threading
from pathlib import Path

from .console import log


class FileWatcher:
    """Poll a directory tree and increment a version when it changes."""

    def __init__(self, root, interval=0.5):
        self.root = root
        self.interval = interval
        self._version = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._previous = self._snapshot()
        self._thread = threading.Thread(
            target=self._watch, name="ownserver-file-watcher", daemon=True
        )

    @property
    def version(self):
        with self._lock:
            return self._version

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=self.interval * 3)

    def _snapshot(self):
        snapshot = {}
        for current_root, directory_names, file_names in os.walk(
            str(self.root), topdown=True, followlinks=False
        ):
            entry_names = [
                name
                for name in directory_names + file_names
                if name != ".git"
            ]
            for name in entry_names:
                path = Path(current_root) / name
                try:
                    stat_result = path.lstat()
                except OSError:
                    continue
                relative_path = str(path.relative_to(self.root))
                snapshot[relative_path] = (
                    stat_result.st_mode,
                    stat_result.st_size,
                    stat_result.st_mtime_ns,
                    stat_result.st_ctime_ns,
                    stat_result.st_ino,
                )

            directory_names[:] = [
                name
                for name in directory_names
                if name != ".git" and not (Path(current_root) / name).is_symlink()
            ]
        return snapshot

    def _watch(self):
        previous = self._previous
        while not self._stop_event.wait(self.interval):
            current = self._snapshot()
            if current != previous:
                previous = current
                with self._lock:
                    self._version += 1
                log(
                    "watch",
                    "Change detected; open HTML pages will reload.",
                    stream=sys.stderr,
                )
