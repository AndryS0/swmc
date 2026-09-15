"""Realtime file watching.

Stormworks rewrites a microprocessor's ``.xml`` whenever you save it in the
in-game editor, and it reads the file back when you open it.  To cooperate with
that we need to notice external writes promptly and never clobber them
silently.

A polling watcher is used on purpose: it needs no third-party package, it works
on network and virtual filesystems where inotify/ReadDirectoryChangesW are
unreliable, and at a 0.4s interval the cost of stat()ing a handful of files is
irrelevant next to being dependency-free.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time

__all__ = ["Signature", "FileWatcher"]


class Signature:
    """Cheap identity of a file on disk: size, mtime and content hash."""

    __slots__ = ("exists", "size", "mtime", "digest")

    def __init__(self, exists=False, size=-1, mtime=-1.0, digest=""):
        self.exists = exists
        self.size = size
        self.mtime = mtime
        self.digest = digest

    @classmethod
    def of(cls, path):
        try:
            st = os.stat(path)
        except OSError:
            return cls()
        try:
            with open(path, "rb") as fh:
                digest = hashlib.sha1(fh.read()).hexdigest()
        except OSError:
            return cls()
        return cls(True, st.st_size, st.st_mtime, digest)

    def __eq__(self, other):
        return (isinstance(other, Signature)
                and self.exists == other.exists
                and self.digest == other.digest)

    def __ne__(self, other):
        return not self.__eq__(other)

    def to_dict(self):
        return {"exists": self.exists, "size": self.size,
                "mtime": self.mtime, "sha1": self.digest[:12]}

    def __repr__(self):
        return "<Signature %s %d %s>" % (self.exists, self.size, self.digest[:8])


class FileWatcher:
    """Polls a set of paths on a background thread and reports what changed.

    Callbacks run on the watcher thread, so they must be quick and must not
    raise; anything that can fail belongs in the queue the caller drains.
    """

    def __init__(self, interval=0.4, on_change=None):
        self.interval = float(interval)
        self.on_change = on_change
        self._paths = {}          # path -> Signature last seen
        self._ignore = {}         # path -> Signature we wrote ourselves
        self._lock = threading.RLock()
        self._thread = None
        self._stop = threading.Event()

    # -- registration -------------------------------------------------------
    def watch(self, path):
        path = os.path.abspath(path)
        with self._lock:
            if path not in self._paths:
                self._paths[path] = Signature.of(path)
        self.start()
        return path

    def unwatch(self, path):
        path = os.path.abspath(path)
        with self._lock:
            self._paths.pop(path, None)
            self._ignore.pop(path, None)

    def watched(self):
        with self._lock:
            return sorted(self._paths)

    def mark_self_write(self, path):
        """Record that *we* just wrote this file, so it is not reported back."""
        path = os.path.abspath(path)
        sig = Signature.of(path)
        with self._lock:
            self._ignore[path] = sig
            if path in self._paths:
                self._paths[path] = sig
        return sig

    def signature(self, path):
        path = os.path.abspath(path)
        with self._lock:
            return self._paths.get(path) or Signature.of(path)

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="swmc-watch", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2.0)
        self._thread = None

    def poll_once(self):
        """Check every watched path now and return the list of change events."""
        events = []
        with self._lock:
            paths = list(self._paths.items())
        for path, old in paths:
            new = Signature.of(path)
            if new == old:
                continue
            with self._lock:
                mine = self._ignore.get(path)
                self._paths[path] = new
                if mine is not None and mine == new:
                    continue
                self._ignore.pop(path, None)
            kind = "created" if not old.exists else ("deleted" if not new.exists
                                                     else "modified")
            events.append({"path": path, "kind": kind, "at": time.time(),
                           "signature": new.to_dict()})
        if events and self.on_change:
            try:
                self.on_change(events)
            except Exception:
                pass
        return events

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                self.poll_once()
            except Exception:
                # A transient stat failure must never kill the watcher thread.
                pass
