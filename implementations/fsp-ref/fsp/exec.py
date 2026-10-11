# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The execution path (EXEC): the native primitives, inside the workspace and
outside the store (OC-008, D15)."""

from __future__ import annotations

import os

from . import config, ledger, sil, vital
from .digest import sha256
from .sil import Refused, log_append
from .store import GuardError, Store, write_host_file


def workspace_of(store: Store):
    """The workspace the Operator declared (OC-008(a)), or ``None``."""
    try:
        data = store.read_json(config.OPERATIONAL)
    except (FileNotFoundError, ValueError):
        return None
    ws = data.get("workspace") if isinstance(data, dict) else None
    return ws if isinstance(ws, str) else None


def _inside(path, root):
    return path == root or path.startswith(root + os.sep)


def _refuse(store, op, target, check, rule, detail):
    rec = log_append(
        store, "refusal", rule=rule, check=check, detail=detail, op=op, target=target
    )
    return Refused(check, rule, detail, [rec])


def boundary(store, op, target):
    """The workspace boundary, the first check of every act on the host
    (OC-008(a)(b), step 8.6). Returns ``(real, rel)``: the resolved target and
    its path relative to the workspace. It runs before the session check and
    before the Vital Check."""
    ws = workspace_of(store)
    if ws is None:
        raise _refuse(
            store,
            op,
            target,
            "workspace-boundary",
            "OC-008(a)",
            "no workspace is declared",
        )
    if not isinstance(target, str) or not target:
        raise _refuse(store, op, target, "workspace-boundary", "OC-008(a)", "no target")
    ws_real = os.path.realpath(ws)
    store_real = os.path.realpath(store.root)
    path = target if os.path.isabs(target) else os.path.join(ws_real, target)
    real = os.path.realpath(path)
    if _inside(real, store_real):
        raise _refuse(
            store,
            op,
            target,
            "workspace-boundary",
            "OC-008(b)",
            "%r is inside the Entity Store" % target,
        )
    if not _inside(real, ws_real):
        raise _refuse(
            store,
            op,
            target,
            "workspace-boundary",
            "OC-008(a)",
            "%r resolves outside the workspace" % target,
        )
    rel = os.path.relpath(real, ws_real).replace(os.sep, "/")
    return real, rel


def _executed(store, session, op, rel, **fields):
    return log_append(
        store,
        "execution",
        rule="OC-008(d)",
        session=session,
        op=op,
        target=rel,
        **fields,
    )


def _failed(store, session, op, rel, error):
    rec = _executed(store, session, op, rel, outcome="failed", error=error)
    return Refused(
        "execution", "OC-008(d)", "%s on %s failed: %s" % (op, rel, error), [rec]
    )


def file_read(root, target):
    """Read a file inside the workspace. Returns its content, size and digest;
    the adapter reports only the size and the digest (D15)."""
    store = Store(root)
    with store.write_lock():
        real, rel = boundary(store, "file_read", target)
        session = vital.require_entity_session(root, "file_read")
        try:
            with open(real, "rb") as f:
                data = f.read()
        except OSError as e:
            raise _failed(store, session, "file_read", rel, str(e))
        digest = sha256(data)
        rec = _executed(
            store,
            session,
            "file_read",
            rel,
            outcome="done",
            size=len(data),
            sha256=digest,
        )
        return {
            "data": data,
            "size": len(data),
            "sha256": digest,
            "target": rel,
            "log_records": [rec],
        }


def file_write(root, target, data, *, intent):
    """Write ``data`` to a file inside the workspace, under an Action Ledger
    entry opened before the write and resolved after it (OP-015, OC-008(d))."""
    store = Store(root)
    with store.write_lock():
        real, rel = boundary(store, "file_write", target)
        session = vital.require_entity_session(root, "file_write")
        entry = ledger.open_entry(
            store, op="file_write", target=rel, intent=intent, session=session
        )
        try:
            write_host_file(real, data, stores=(store.root,))
        except (OSError, GuardError) as e:
            ledger.resolve_entry(store, entry, "failed", session=session, error=str(e))
            raise _failed(store, session, "file_write", rel, str(e))
        ledger.resolve_entry(store, entry, "done", session=session)
        rec = _executed(
            store,
            session,
            "file_write",
            rel,
            outcome="done",
            size=len(data),
            sha256=sha256(data),
            ledger=entry,
        )
        return {
            "size": len(data),
            "sha256": sha256(data),
            "target": rel,
            "ledger": entry,
            "log_records": [rec],
        }


def file_list(root, target):
    """List the names in a directory inside the workspace, sorted."""
    store = Store(root)
    with store.write_lock():
        real, rel = boundary(store, "file_list", target)
        session = vital.require_entity_session(root, "file_list")
        try:
            names = sorted(os.listdir(real))
        except OSError as e:
            raise _failed(store, session, "file_list", rel, str(e))
        rec = _executed(
            store, session, "file_list", rel, outcome="done", count=len(names)
        )
        return {"entries": names, "target": rel, "log_records": [rec]}


def attempt_file_write(store: Store, cls, target):
    """file_write's attempted write: a host operation writes no content class
    of the store, so it refuses every one (D68)."""
    raise sil.refuse_attempt(
        store,
        "sole-writer",
        "file_write writes the workspace, no content class of the store",
        via="file_write",
        content_class=cls,
        target=target,
    )


def attempt_file_read(store: Store, cls, target):
    """file_read's attempted write: a host operation writes no content class
    of the store, so it refuses every one (D68)."""
    raise sil.refuse_attempt(
        store,
        "sole-writer",
        "file_read reads the workspace and writes no content class of the store",
        via="file_read",
        content_class=cls,
        target=target,
    )


def attempt_file_list(store: Store, cls, target):
    """file_list's attempted write: a host operation writes no content class
    of the store, so it refuses every one (D68)."""
    raise sil.refuse_attempt(
        store,
        "sole-writer",
        "file_list lists the workspace and writes no content class of the store",
        via="file_list",
        content_class=cls,
        target=target,
    )
