"""Fault injection (ADAPTER.md §5). Corrupts the store the way a fault or a
careless hand would: directly on disk, bypassing every guard — that is the
point. Nothing in ``fsp`` imports this module.
"""

from __future__ import annotations

import os
import secrets

from fsp import chain
from fsp.adapter import CannotAttempt, NotImplementedCommand, accepted
from fsp.digest import canonical
from fsp.verify import verify


def _active(root):
    r = verify(root)
    if r.state != "active" or r.head_entry is None:
        raise CannotAttempt("%s is not an active fsp store" % root)
    return r


def _raw_replace(path, data):
    with open(path, "wb") as f:
        f.write(data)


def _structural_byte(root, r):
    rel = chain.gen_relpath(r.head_entry) + "/persona.md"
    path = os.path.join(root, rel)
    with open(path, "rb") as f:
        data = bytearray(f.read())
    i = len(data) // 2
    data[i] ^= 0x01
    _raw_replace(path, bytes(data))
    return {"target": rel, "offset": i}


def _chain_entry_removed(root, r):
    k = 1 if r.head_entry >= 1 else 0
    rel = chain.entry_relpath(k)
    os.unlink(os.path.join(root, rel))
    return {"target": rel}


def _chain_entry_forged(root, r):
    """Append an entry whose predecessor does not exist, and point ``HEAD``
    at it, as a forger would: the content digest is right, the link is not."""
    n = r.head_entry + 1
    body = chain.commit(
        n=n,
        predecessor="sha256:" + secrets.token_hex(32),
        state_digest=r.head_digest,
        authorization="forged",
        at="1970-01-01T00:00:00Z",
    )
    _raw_replace(os.path.join(root, chain.entry_relpath(n)), canonical(body))
    os.link(
        os.path.join(root, chain.document_relpath(r.head_entry)),
        os.path.join(root, chain.document_relpath(n)),
    )
    os.rename(
        os.path.join(root, chain.gen_relpath(r.head_entry)),
        os.path.join(root, chain.gen_relpath(n)),
    )
    head = chain.head(entry=n, entry_id=chain.entry_id(body), baseline=r.head_digest)
    _raw_replace(os.path.join(root, chain.HEAD), canonical(head))
    return {"target": chain.entry_relpath(n)}


CORRUPTIONS = {
    "structural-byte": _structural_byte,
    "chain-entry-removed": _chain_entry_removed,
    "chain-entry-forged": _chain_entry_forged,
    # commit-unauthorized needs recorded authorizations to be meaningful
    # (Phase 2); skill-file and skill-manifest need skills (Phase 5).
}


def corrupt(root, flags):
    kind = flags.get("kind")
    fn = CORRUPTIONS.get(kind)
    if fn is None:
        raise NotImplementedCommand("inject corrupt --kind %s" % kind)
    return accepted(dict(fn(root, _active(root)), kind=kind))
