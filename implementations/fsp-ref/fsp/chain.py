"""Formats of the integrity chain, the integrity documents and ``HEAD``.

Every one is stored as canonical JSON, so a file's identity is the sha256 of
its bytes. An entry's **id** is that digest; each later entry names its
predecessor by id; ``HEAD`` names the entry it points at by id. Changing any
byte of any committed entry therefore breaks a link somewhere (OC-004(a)).
The id of the Genesis Anchor is the entity's ``genesis_digest``.
"""

from __future__ import annotations

from .digest import canonical, sha256

HEAD = "HEAD"


def entry_relpath(n: int) -> str:
    return "integrity/chain/%06d.json" % n


def document_relpath(n: int) -> str:
    return "integrity/documents/%d.json" % n


def gen_relpath(n: int) -> str:
    return "structural/gen/%d" % n


def entry_id(body: dict) -> str:
    return sha256(canonical(body))


def genesis(*, state_digest, binding, version, major, nonce, at, implementation):
    """The Genesis Anchor (OC-004(a)). ``nonce`` makes two entities founded
    on identical content distinct: re-initializing creates a new, unrelated
    entity (OP-017)."""
    return {
        "entry": 0,
        "kind": "genesis",
        "state_digest": state_digest,
        "binding": binding,
        "version": version,
        "major": major,
        "nonce": nonce,
        "at": at,
        "implementation": implementation,
    }


def commit(*, n, predecessor, state_digest, authorization, at, version=None):
    body = {
        "entry": n,
        "kind": "commit" if version is None else "version-transition",
        "predecessor": predecessor,
        "state_digest": state_digest,
        "authorization": authorization,
        "at": at,
    }
    if version is not None:
        body["version"] = version
    return body


def head(*, entry, entry_id, baseline):
    return {"entry": entry, "entry_id": entry_id, "baseline": baseline}
