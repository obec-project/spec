"""The Entity Store on disk: layout, the two write forms, and the class guard.

Every write to the store goes through this module (DEV-NOTES §2). A write
names the content class it writes and the writer performing it; the guard
refuses when the path does not belong to that class, or the writer is not the
class's sole writer (OC-003(c), OC-005(a)). A unit test scans the rest of the
code for raw writes.

Two write forms, and only two (DEV-NOTES §3.1):

- **append** — one canonical JSON record per line, ``O_APPEND``, ``fsync``
  per record; a truncated final line is detected on read, never repaired.
- **replace** — the whole file: temp file in the same directory, ``fsync``,
  ``rename``, ``fsync`` of the directory.

No store file is ever rewritten in place.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import json
import os
import re
import shutil
import threading

from .digest import canonical

STRUCTURAL = "structural"
MNEMONIC = "mnemonic"
INTEGRITY = "integrity"
CLASSES = (STRUCTURAL, MNEMONIC, INTEGRITY)

# The sole writer of each class, and the operation that is its write path.
OWNER = {
    STRUCTURAL: ("sil.commit", "commit"),
    INTEGRITY: ("sil", "integrity-write"),
    MNEMONIC: ("mil", "mnemonic-save"),
}


class Datum:
    __slots__ = ("name", "pattern", "cls", "form", "regex")

    def __init__(self, name, pattern, cls, form):
        self.name = name
        self.pattern = pattern  # relative to the store; <x> is a placeholder
        self.cls = cls
        self.form = form  # "replace" | "append" | "exclusive" | "tree"
        rx = re.escape(pattern)
        rx = rx.replace(re.escape("<n>"), r"[0-9]+")
        rx = rx.replace(re.escape("<nnnnnn>"), r"[0-9]{6}")
        rx = rx.replace(re.escape("<id>"), r"[A-Za-z0-9._-]+")
        rx = rx.replace(re.escape("<path>"), r"[A-Za-z0-9_][A-Za-z0-9._/-]*")
        self.regex = re.compile("^" + rx + "$")


# Everything the implementation persists inside the store (DEV-NOTES §3.1).
# `describe state` is generated from this table, and a file matching no entry
# is a datum without a class — reported by verification.
LAYOUT = (
    Datum("store-marker", "OBEC-STORE", INTEGRITY, "replace"),
    Datum("passive-signal", "PASSIVE-SIGNAL", INTEGRITY, "replace"),
    Datum("session-credential", "CREDENTIAL", INTEGRITY, "exclusive"),
    Datum("pulse", "PULSE", INTEGRITY, "replace"),
    Datum("head", "HEAD", INTEGRITY, "replace"),
    Datum("structural-content", "structural/gen/<n>/<path>", STRUCTURAL, "tree"),
    Datum("integrity-chain", "integrity/chain/<nnnnnn>.json", INTEGRITY, "replace"),
    Datum("integrity-documents", "integrity/documents/<n>.json", INTEGRITY, "replace"),
    Datum("integrity-log", "integrity/log.jsonl", INTEGRITY, "append"),
    Datum("authorization-state", "integrity/auth.json", INTEGRITY, "replace"),
    Datum("operational-settings", "integrity/operational.json", INTEGRITY, "replace"),
    Datum("action-ledger", "integrity/ledger.jsonl", INTEGRITY, "append"),
    Datum("session-store", "memory/session/<id>.jsonl", MNEMONIC, "append"),
    Datum("episodic-memory", "memory/episodic/records.jsonl", MNEMONIC, "append"),
    Datum("semantic-memory", "memory/semantic/records.jsonl", MNEMONIC, "append"),
)

MARKER = "OBEC-STORE"
STORE_FORMAT = "fsp-store"
STORE_FORMAT_VERSION = 1


class GuardError(Exception):
    """A write refused by the class guard. Carries the check that refused."""

    def __init__(self, check, detail):
        super().__init__(detail)
        self.check = check
        self.detail = detail


def datum_of(relpath: str):
    for d in LAYOUT:
        if d.regex.match(relpath):
            return d
    return None


def class_of(relpath: str):
    d = datum_of(relpath)
    return d.cls if d else None


def _check_relpath(relpath: str) -> str:
    if (
        not relpath
        or relpath.startswith("/")
        or "\\" in relpath
        or any(p in ("", ".", "..") for p in relpath.split("/"))
    ):
        raise GuardError("store-path", "not a normalized store-relative path: %r" % relpath)
    return relpath


def _fsync_dir(path: str) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Store:
    """One Entity Store. Safe to share between threads of one process; the
    write lock also excludes other processes (``flock`` on the store
    directory itself, so the lock is not a datum)."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self._lock = threading.RLock()
        self._depth = 0
        self._lock_fd = None

    # -- paths ------------------------------------------------------------

    def path(self, relpath: str) -> str:
        return os.path.join(self.root, *_check_relpath(relpath).split("/"))

    def exists(self, relpath: str) -> bool:
        return os.path.lexists(self.path(relpath))

    def listdir(self, reldir: str):
        try:
            return sorted(os.listdir(self.path(reldir)))
        except FileNotFoundError:
            return []

    # -- the write lock ---------------------------------------------------

    @contextlib.contextmanager
    def write_lock(self):
        """Reentrant within a thread; exclusive across threads and processes."""
        with self._lock:
            if self._depth == 0:
                fd = os.open(self.root, os.O_RDONLY)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                except BaseException:
                    os.close(fd)
                    raise
                self._lock_fd = fd
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                if self._depth == 0:
                    fd, self._lock_fd = self._lock_fd, None
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)

    # -- the guard --------------------------------------------------------

    def _guard(self, cls: str, relpath: str, writer: str, form: str):
        _check_relpath(relpath)
        if cls not in CLASSES:
            raise GuardError("content-class", "unknown content class %r" % cls)
        d = datum_of(relpath)
        if d is None:
            raise GuardError("content-class", "%s is not a datum of any class" % relpath)
        if d.cls != cls:
            raise GuardError(
                "content-class", "%s is %s content, not %s" % (relpath, d.cls, cls)
            )
        owner, _op = OWNER[cls]
        if writer != owner:
            raise GuardError(
                "sole-writer", "%s content has one writer (%s), not %s" % (cls, owner, writer)
            )
        if form != d.form and not (d.form == "tree" and form == "replace"):
            raise GuardError(
                "write-form", "%s is written by %s, not %s" % (relpath, d.form, form)
            )

    def _makedirs(self, absdir: str) -> None:
        if os.path.isdir(absdir):
            return
        parent = os.path.dirname(absdir)
        self._makedirs(parent)
        try:
            os.mkdir(absdir)
        except FileExistsError:
            return
        _fsync_dir(parent)

    # -- the two write forms ----------------------------------------------

    def replace(self, cls, relpath, data: bytes, *, writer, executable=False):
        """Replace a whole file atomically."""
        self._guard(cls, relpath, writer, "replace")
        target = self.path(relpath)
        with self.write_lock():
            directory = os.path.dirname(target)
            self._makedirs(directory)
            tmp = os.path.join(
                directory, ".%s.tmp-%d" % (os.path.basename(target), os.getpid())
            )
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.fchmod(fd, 0o755 if executable else 0o644)
                view = memoryview(data)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.rename(tmp, target)
            _fsync_dir(directory)

    def replace_json(self, cls, relpath, obj, *, writer):
        self.replace(cls, relpath, canonical(obj), writer=writer)

    def append(self, cls, relpath, record: dict, *, writer) -> None:
        """Append one record as a canonical JSON line."""
        self._guard(cls, relpath, writer, "append")
        line = canonical(record) + b"\n"
        target = self.path(relpath)
        with self.write_lock():
            directory = os.path.dirname(target)
            self._makedirs(directory)
            created = not os.path.exists(target)
            fd = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                view = memoryview(line)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
            if created:
                _fsync_dir(directory)

    def create_exclusive(self, cls, relpath, data: bytes, *, writer) -> bool:
        """Create a file that must not exist (``O_EXCL``). False if it did."""
        self._guard(cls, relpath, writer, "exclusive")
        target = self.path(relpath)
        with self.write_lock():
            try:
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                return False
            try:
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            _fsync_dir(os.path.dirname(target))
            return True

    def remove(self, cls, relpath, *, writer) -> bool:
        """Remove one file, or a whole structural generation directory. Only
        the owner of the class may; append-only data is never removed."""
        _check_relpath(relpath)
        if re.match(r"^structural/gen/[0-9]+$", relpath):
            if cls != STRUCTURAL:
                raise GuardError("content-class", "%s is structural content" % relpath)
            if writer != OWNER[STRUCTURAL][0]:
                raise GuardError("sole-writer", "structural content has one writer")
        else:
            d = datum_of(relpath)
            if d is not None and d.form == "append":
                raise GuardError("append-only", "%s is append-only" % relpath)
            self._guard(cls, relpath, writer, d.form if d and d.form != "tree" else "replace")
        target = self.path(relpath)
        with self.write_lock():
            try:
                if os.path.isdir(target) and not os.path.islink(target):
                    shutil.rmtree(target)
                else:
                    os.unlink(target)
            except FileNotFoundError:
                return False
            _fsync_dir(os.path.dirname(target))
            return True

    def remove_fap_residue(self, *, writer) -> None:
        """Remove what an interrupted first activation left. Only valid while
        no ``HEAD`` exists: before it, nothing was ever committed (OP-017)."""
        if writer != OWNER[INTEGRITY][0]:
            raise GuardError("sole-writer", "first activation belongs to the SIL")
        with self.write_lock():
            if self.exists("HEAD"):
                raise GuardError("first-activation", "store is active; nothing is residue")
            for name in ("structural", "integrity", "memory"):
                target = os.path.join(self.root, name)
                if os.path.isdir(target):
                    shutil.rmtree(target)
            for name in os.listdir(self.root):
                if name.startswith(".") and ".tmp-" in name:
                    os.unlink(os.path.join(self.root, name))
            _fsync_dir(self.root)

    # -- reading ----------------------------------------------------------

    def read_bytes(self, relpath: str) -> bytes:
        with open(self.path(relpath), "rb") as f:
            return f.read()

    def read_json(self, relpath: str):
        return json.loads(self.read_bytes(relpath).decode("utf-8"))

    def read_jsonl(self, relpath: str):
        """Returns ``(records, truncated)``. A final line without its newline
        is a torn append: reported, never parsed as a record."""
        try:
            data = self.read_bytes(relpath)
        except FileNotFoundError:
            return [], False
        truncated = bool(data) and not data.endswith(b"\n")
        lines = data.split(b"\n")
        lines = lines[:-1]  # the fragment after the last newline, or ""
        return [json.loads(line.decode("utf-8")) for line in lines], truncated

    def read_last_jsonl(self, relpath: str):
        """The last complete record, reading from the end (OP-019: cost does
        not grow with the log)."""
        try:
            fd = os.open(self.path(relpath), os.O_RDONLY)
        except FileNotFoundError:
            return None
        try:
            buf = b""
            pos = os.fstat(fd).st_size
            while pos > 0:
                step = min(1 << 16, pos)
                pos -= step
                buf = os.pread(fd, step, pos) + buf
                end = buf.rfind(b"\n")  # anything after it is a torn append
                if end == -1:
                    continue
                start = buf.rfind(b"\n", 0, end)
                if start != -1 or pos == 0:
                    return json.loads(buf[start + 1 : end].decode("utf-8"))
            return None
        finally:
            os.close(fd)


def write_host_file(path: str, data: bytes, *, stores=()) -> None:
    """Atomic write of a file **outside** any Entity Store — host-level
    configuration, an entity folder's git metadata. Refused inside a store."""
    real = os.path.realpath(path)
    for s in stores:
        root = os.path.realpath(s)
        if real == root or real.startswith(root + os.sep):
            raise GuardError("store-boundary", "%s is inside an Entity Store" % path)
    directory = os.path.dirname(real)
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(directory, ".%s.tmp-%d" % (os.path.basename(real), os.getpid()))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.rename(tmp, real)
    _fsync_dir(directory)


def create_store_dir(root: str) -> None:
    """Create the store directory itself (it holds no datum yet)."""
    parent = os.path.dirname(os.path.abspath(root))
    os.makedirs(root, exist_ok=True)
    _fsync_dir(parent)


def is_empty_dir(path: str) -> bool:
    try:
        return not os.listdir(path)
    except FileNotFoundError:
        return True
    except OSError as e:
        if e.errno == errno.ENOTDIR:
            return False
        raise
