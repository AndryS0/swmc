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
from typing import Callable, Dict, List, Optional

__all__ = ["Signature", "FileWatcher"]


class Signature:
    """Cheap identity of a file on disk: size, mtime and content hash."""

    __slots__ = ("exists", "size", "mtime", "digest")

    def __init__(self, exists: bool = False, size: int = -1,
                 mtime: float = -1.0, digest: str = "") -> None:
        self.exists = exists
        self.size = size
        self.mtime = mtime
        self.digest = digest

    @classmethod
    def of(cls, path: str) -> "Signature":
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

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, Signature)
                and self.exists == other.exists
                and self.digest == other.digest)

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def to_dict(self) -> "Dict[str, object]":
        return {"exists": self.exists, "size": self.size,
                "mtime": self.mtime, "sha1": self.digest[:12]}

    def __repr__(self) -> str:
        return "<Signature %s %d %s>" % (self.exists, self.size, self.digest[:8])


class FileWatcher:
    """Polls a set of paths and reports what changed.

    There are two ways to use it, and they must not be mixed:

    * **Callback.** Pass ``on_change``; :meth:`watch` then starts a background
      thread that polls and hands events to it. Callbacks run on that thread,
      so they must be quick and must not raise.
    * **Manual.** Leave ``on_change`` as ``None`` and call :meth:`poll_once`
      yourself. No thread is started.

    A watcher with no callback deliberately does *not* start polling on its
    own: an event is consumed by whoever observes it first, so a background
    thread running alongside a caller's ``poll_once()`` loop would swallow
    changes at random. If you want both, use the callback form and let it fill
    a queue.
    """

    def __init__(self, interval: float = 0.4,
                 on_change: "Optional[Callable[[List[dict]], None]]" = None) -> None:
        self.interval = float(interval)
        self.on_change = on_change
        #: path -> signature last seen
        self._paths: "Dict[str, Signature]" = {}
        #: path -> signature we wrote ourselves
        self._ignore: "Dict[str, Signature]" = {}
        self._lock = threading.RLock()
        self._thread: "Optional[threading.Thread]" = None
        self._stop = threading.Event()

    # -- registration -------------------------------------------------------
    def watch(self, path: str) -> str:
        path = os.path.abspath(path)
        with self._lock:
            if path not in self._paths:
                self._paths[path] = Signature.of(path)
        if self.on_change is not None:
            self.start()
        return path

    def unwatch(self, path: str) -> None:
        path = os.path.abspath(path)
        with self._lock:
            self._paths.pop(path, None)
            self._ignore.pop(path, None)

    def watched(self) -> "List[str]":
        with self._lock:
            return sorted(self._paths)

    def mark_self_write(self, path: str) -> "Signature":
        """Record that *we* just wrote this file, so it is not reported back."""
        path = os.path.abspath(path)
        sig = Signature.of(path)
        with self._lock:
            self._ignore[path] = sig
            if path in self._paths:
                self._paths[path] = sig
        return sig

    def signature(self, path: str) -> "Signature":
        path = os.path.abspath(path)
        with self._lock:
            return self._paths.get(path) or Signature.of(path)

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="swmc-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2.0)
        self._thread = None

    def poll_once(self) -> "List[dict]":
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

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.poll_once()
            except Exception:
                # A transient stat failure must never kill the watcher thread.
                pass
