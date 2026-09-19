"""The System Integrity Layer: the one writer of integrity content, and the
committer of structural content (OC-003(c), OC-005(a)).

Phase 1: the integrity log, scaffolding and First Activation (D29). Commit,
gates, credential and the Vital Check come in later phases, here.
"""

from __future__ import annotations

import os
import re
import secrets

from . import OBEC_MAJOR, OBEC_VERSION, __version__, chain, clock
from .digest import canonical, document_digest, integrity_document, sha256
from .store import (
    INTEGRITY,
    MARKER,
    STORE_FORMAT,
    STORE_FORMAT_VERSION,
    STRUCTURAL,
    Store,
    create_store_dir,
    is_empty_dir,
)

WRITER = "sil"
COMMITTER = "sil.commit"

LOG = "integrity/log.jsonl"

BINDING_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,127}$")

DEFAULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "defaults")


class Refused(Exception):
    """An act the SIL refused. ``log_records`` holds the ids of the records
    that logged the refusal, when the store could take one."""

    def __init__(self, check, rule, detail, log_records=()):
        super().__init__(detail)
        self.check = check
        self.rule = rule
        self.detail = detail
        self.log_records = list(log_records)


# -- a credential found at start (D25, OC-003(d)) ---------------------------

LOCK_HELD = "held"  # another process holds the credential's flock
LOCK_FREE = "free"  # we took it: no process holds it
LOCK_UNKNOWN = "unknown"  # the filesystem would not say


def classify_credential(lock, *, residue, pulse_fresh):
    """``"conflict"`` or ``"crash"`` for a credential present at start.

    The operating system's lock takes absolute precedence: while a process
    holds it, or while its state cannot be established, the session is live
    and nothing else is consulted — not residue (a live session mid-commit
    has some) and not the ``PULSE`` (a live process can be slow to touch
    it). Only a free lock lets the rest decide: residue of interrupted work
    means a crash; otherwise a fresh ``PULSE`` means a session live without
    a process (ADAPTER.md §2.5), and a stale one a crash.
    """
    if lock not in (LOCK_HELD, LOCK_FREE, LOCK_UNKNOWN):
        raise ValueError("lock state %r" % (lock,))
    if lock != LOCK_FREE:
        return "conflict"
    if residue:
        return "crash"
    return "conflict" if pulse_fresh else "crash"


# -- the integrity log (DEV-NOTES §3.4) -------------------------------------


def log_append(store: Store, kind, *, rule=None, binding=None, session=None, **payload):
    """Append one record to the integrity log and return its id. Each record
    carries the digest of the one before it, so an edit to history breaks
    the sequence where it happened."""
    with store.write_lock():
        last = store.read_last_jsonl(LOG)
        seq = int(last["id"].split("-")[1]) + 1 if last else 1
        record = dict(payload)
        record.update(
            {
                "id": "L-%06d" % seq,
                "kind": kind,
                "at": clock.iso(),
                "prev": sha256(canonical(last)) if last else None,
            }
        )
        if rule is not None:
            record["rule"] = rule
        if binding is not None:
            record["binding"] = binding
        if session is not None:
            record["session"] = session
        store.append(INTEGRITY, LOG, record, writer=WRITER)
        return record["id"]


# -- scaffolding (D27) and First Activation (D29) ---------------------------


def scaffold_store(root: str, *, model=None) -> Store:
    """Create an empty store: the directory and its marker, nothing else.
    No Genesis, no ``HEAD`` — the store is *scaffolded*, not an entity."""
    root = os.path.abspath(root)
    if os.path.lexists(os.path.join(root, MARKER)):
        return Store(root)
    if not is_empty_dir(root):
        raise Refused(
            "first-activation",
            "OP-017",
            "%s is neither empty nor an fsp store; refusing to touch it" % root,
        )
    create_store_dir(root)
    store = Store(root)
    marker = {
        "format": STORE_FORMAT,
        "format_version": STORE_FORMAT_VERSION,
        "implementation": "fsp-ref",
    }
    if model is not None:
        marker["model"] = model  # the init choice; the FAP logs it as an act
    store.replace(INTEGRITY, MARKER, canonical(marker), writer=WRITER)
    return store


def _default(name: str) -> bytes:
    with open(os.path.join(DEFAULTS, name), "rb") as f:
        return f.read()


def initial_structure(*, name: str, operator: str, persona: bytes = None):
    """The complete initial structural state, as ``{relpath: bytes}``."""
    return {
        "persona.md": persona if persona is not None else _default("persona.md"),
        "config.json": canonical({"name": name}),
        "bindings.json": canonical({"bindings": [{"id": operator}]}),
        "rules.json": canonical({"default": "hold", "domains": {}, "skills": {}}),
        "probes.json": _default("probes.json"),
    }


def first_activation(root: str, operator: str, *, name="entity", persona=None, model=None):
    """First Activation Protocol (D29, OP-017).

    Runs exactly once. Writes the founding Operator binding, the initial
    structural state, its integrity document, the Genesis Anchor and the log
    records of the founding acts — then ``HEAD``, the single atomic point.
    Before ``HEAD`` exists the store is not an entity, and whatever an earlier
    interrupted activation left is removed first. No session credential is
    issued here: the first one comes from a start that runs every gate.
    """
    if not BINDING_ID.match(operator or ""):
        raise Refused("binding", "OC-002(a)", "invalid Operator binding id %r" % operator)
    store = scaffold_store(root, model=model)
    with store.write_lock():
        if store.exists(chain.HEAD):
            rec = log_append(
                store,
                "refusal",
                rule="OP-017",
                check="first-activation",
                detail="first activation already ran on this store",
            )
            raise Refused(
                "first-activation",
                "OP-017",
                "first activation already ran; re-initializing would create a new entity",
                [rec],
            )
        store.remove_fap_residue(writer=WRITER)
        marker = store.read_json(MARKER)

        gen = chain.gen_relpath(0)
        for rel, data in sorted(initial_structure(name=name, operator=operator, persona=persona).items()):
            store.replace(STRUCTURAL, gen + "/" + rel, data, writer=COMMITTER)

        document, problems = integrity_document(store.path(gen))
        assert not problems, problems
        store.replace(INTEGRITY, chain.document_relpath(0), canonical(document), writer=WRITER)
        state_digest = document_digest(document)

        at = clock.iso()
        anchor = chain.genesis(
            state_digest=state_digest,
            binding=operator,
            version=OBEC_VERSION,
            major=OBEC_MAJOR,
            nonce=secrets.token_hex(16),
            at=at,
            implementation="fsp-ref " + __version__,
        )
        store.replace(INTEGRITY, chain.entry_relpath(0), canonical(anchor), writer=WRITER)
        genesis_id = chain.entry_id(anchor)

        records = [
            log_append(
                store,
                "operator-act",
                rule="OC-002(a)",
                binding=operator,
                act="found",
                detail="founding Operator binding established at first activation",
            )
        ]
        if "model" in marker:
            records.append(
                log_append(
                    store,
                    "operator-act",
                    rule="OC-002(a)",
                    binding=operator,
                    act="set-model",
                    model=marker["model"],
                )
            )
        records.append(
            log_append(
                store,
                "genesis",
                rule="OC-004(a)",
                binding=operator,
                genesis_digest=genesis_id,
                state_digest=state_digest,
                version=OBEC_VERSION,
            )
        )

        head = chain.head(entry=0, entry_id=genesis_id, baseline=state_digest)
        store.replace(INTEGRITY, chain.HEAD, canonical(head), writer=WRITER)

    return {
        "genesis_digest": genesis_id,
        "head_digest": state_digest,
        "log_records": records,
    }
