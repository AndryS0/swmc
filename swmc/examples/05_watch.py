"""React to the game saving a microprocessor under you.

    python examples/05_watch.py "Complex Helicopter Gyro.xml"
    python examples/05_watch.py --demo out.xml     # writes to it, then exits

Stormworks rewrites the whole file when you save in the editor. The watcher
polls (no third-party package, and it behaves on network and synced drives
where native notifications do not), hashes the contents, and tells you what
changed.
"""

import shutil
import sys
import threading
import time

from swmc import Microprocessor
from swmc.watch import FileWatcher


def describe(path):
    try:
        doc = Microprocessor.load(path)
    except Exception as exc:
        return "unreadable: %s" % exc
    return "%d components, %d io pins, %d issue(s)" % (
        len(doc.components), len(doc.io_pins), len(doc.validate()))


def main(argv):
    demo = argv[0] == "--demo"
    if demo:
        argv = argv[1:]
    path = argv[0]

    watcher = FileWatcher(interval=0.3)
    watcher.watch(path)
    print("watching %s" % path)
    print("  now: %s" % describe(path))

    if demo:
        # Stand in for the game: rewrite the file from another thread.
        def edit_it():
            time.sleep(0.8)
            doc = Microprocessor.load(path)
            doc.add("abs", 40, 40)
            doc.save(path)
        threading.Thread(target=edit_it, daemon=True).start()

    deadline = time.time() + (6 if demo else 1e9)
    try:
        while time.time() < deadline:
            for ev in watcher.poll_once():
                print("%s  %-9s %s"
                      % (time.strftime("%H:%M:%S"), ev["kind"], ev["signature"]["sha1"]))
                if ev["kind"] != "deleted":
                    print("            %s" % describe(ev["path"]))
                if demo:
                    deadline = 0            # one event is enough for the demo
                    break
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        watcher.stop()

    # A watcher also fingerprints your own writes so they are not reported
    # back to you as somebody else's change:
    if demo:
        watcher2 = FileWatcher(interval=0.3)
        watcher2.watch(path)
        doc = Microprocessor.load(path)
        doc.add("abs", 41, 41)
        doc.save(path)
        watcher2.mark_self_write(path)
        time.sleep(0.5)
        print("after mark_self_write, events: %r" % (watcher2.poll_once(),))
        watcher2.stop()
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
