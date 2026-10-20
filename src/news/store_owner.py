"""One serialized transaction owner per canonical path, including other processes.

Readers observe a complete old or new document. Never truncate a live file.
The OS releases locks on process exit; the lock file is not a PID lease.
"""
from contextlib import contextmanager
from pathlib import Path
import os
import tempfile
import threading
import time

_owners = {}
_registry_lock = threading.Lock()


class CanonicalStoreOwner:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.lock = threading.RLock()

    @contextmanager
    def transaction(self, timeout=5.0):
        deadline = time.monotonic() + timeout
        if not self.lock.acquire(timeout=timeout):
            raise TimeoutError('canonical store owner busy')
        handle = None
        locked = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(str(self.path) + '.lock', 'a+b')
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b'0'); handle.flush()
            while True:
                try:
                    handle.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except (OSError, BlockingIOError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError('canonical store process owner busy')
                    time.sleep(.01)
            yield
        finally:
            if handle is not None:
                if locked:
                    handle.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()
            self.lock.release()

    def publish(self, text):
        """Called only under transaction; replace is the publication boundary."""
        descriptor, name = tempfile.mkstemp(prefix=self.path.name+'.', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                handle.write(text); handle.flush(); os.fsync(handle.fileno())
            deadline = time.monotonic() + .5
            while True:
                try:
                    os.replace(name, self.path)
                    break
                except PermissionError:  # Windows reader currently has the old file open.
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.01)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def owner_for(path):
    key = os.path.normcase(str(Path(path).resolve()))
    with _registry_lock:
        if key not in _owners:
            _owners[key] = CanonicalStoreOwner(key)
        return _owners[key]
