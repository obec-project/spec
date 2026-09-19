"""Canonical form and digests.

Everything the store hashes is hashed in one canonical form, so that a digest
depends on content alone — never on the host, the filesystem, or the order in
which a directory happens to list (OC-003(b)).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat

# One path segment of structural content. Deliberately narrow: names travel
# between filesystems (case, normalization) and must hash the same everywhere.
SEGMENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")


def canonical(obj) -> bytes:
    """Canonical JSON: sorted keys, no whitespace, UTF-8."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def valid_relpath(relpath: str) -> bool:
    parts = relpath.split("/")
    return bool(parts) and all(SEGMENT.match(p) for p in parts)


def integrity_document(root: str):
    """The integrity document of a structural generation directory (D34).

    Returns ``(document, problems)``. ``document`` is the list of
    ``{path, sha256, exec}`` for every regular file under ``root``, sorted by
    path. ``problems`` lists what cannot be part of structural content — a
    symbolic link, a special file, a name outside ``SEGMENT`` — each as
    ``{path, problem}``; such an entry is never hashed as if it were content.
    """
    document = []
    problems = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/") + "/"
        for name in list(dirnames):
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                problems.append({"path": rel_dir + name, "problem": "symlink"})
                dirnames.remove(name)
            elif not SEGMENT.match(name):
                problems.append({"path": rel_dir + name, "problem": "bad-name"})
                dirnames.remove(name)
        for name in filenames:
            rel = rel_dir + name
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            if stat.S_ISLNK(st.st_mode):
                problems.append({"path": rel, "problem": "symlink"})
            elif not stat.S_ISREG(st.st_mode):
                problems.append({"path": rel, "problem": "not-a-regular-file"})
            elif not SEGMENT.match(name):
                problems.append({"path": rel, "problem": "bad-name"})
            else:
                document.append(
                    {
                        "path": rel,
                        "sha256": sha256_file(full),
                        "exec": bool(st.st_mode & stat.S_IXUSR),
                    }
                )
    document.sort(key=lambda e: e["path"].encode("utf-8"))
    problems.sort(key=lambda e: e["path"].encode("utf-8"))
    return document, problems


def document_digest(document) -> str:
    """The structural digest: sha256 of the canonical integrity document. It
    is the baseline in ``HEAD`` and the ``state_digest`` of the chain entry."""
    return sha256(canonical(document))
