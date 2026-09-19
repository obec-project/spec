"""Verification of committed structural content against the chain (OC-004(a)).

One function serves the start gate, ``lifecycle verify`` and, later, the
Vital Check (D37). It never repairs anything: it returns **findings**, each
``{type, target, owner, evidence}``, and the caller decides. ``owner`` is the
component whose authority covers the correction (DEV-NOTES §6.7).

Only what is committed is verified. Residue of an interrupted commit — an
entry, document or generation beyond ``HEAD`` — is not committed state; it is
reported apart, and removed by the recovery gate.

Every datum read here travels with the store and every path is
store-relative, so the result is the same on any host (OC-003(b)).
"""

from __future__ import annotations

import json
import os
import re

from . import chain
from .digest import canonical, document_digest, integrity_document, valid_relpath
from .store import MARKER, STORE_FORMAT, STORE_FORMAT_VERSION, Store, datum_of


class Finding:
    __slots__ = ("type", "target", "owner", "evidence")

    def __init__(self, type, target, owner, evidence):
        self.type = type
        self.target = target
        self.owner = owner
        self.evidence = evidence

    def as_dict(self):
        return {
            "type": self.type,
            "target": self.target,
            "owner": self.owner,
            "evidence": self.evidence,
        }


class Report:
    def __init__(self):
        self.state = "absent"  # absent | foreign | scaffolded | active
        self.findings = []
        self.residue = []
        self.chain_intact = False
        self.content_matches = False
        self.genesis_digest = None
        self.head_digest = None
        self.entry_count = 0
        self.head_entry = None
        self.entries = []  # (id, body) for 0..HEAD, as far as readable

    @property
    def verified(self):
        return self.state == "active" and not self.findings

    def as_dict(self):
        return {
            "state": self.state,
            "chain_intact": self.chain_intact,
            "content_matches": self.content_matches,
            "genesis_digest": self.genesis_digest,
            "head_digest": self.head_digest,
            "entry_count": self.entry_count,
            "findings": [f.as_dict() for f in self.findings],
            "residue": self.residue,
        }


def _owner_of_structural(relpath):
    # Skill files are the execution path's to prune (OP-006); anything else
    # structural has no correction short of the Operator.
    return "exec" if relpath.startswith("skills/") else "sil"


def _read_canonical(store: Store, relpath: str):
    """Parse a canonical JSON artifact. Returns ``(obj, problem)``."""
    try:
        data = store.read_bytes(relpath)
    except FileNotFoundError:
        return None, "missing"
    except IsADirectoryError:
        return None, "not-a-file"
    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, "unparseable"
    if canonical(obj) != data:
        return None, "not-canonical"
    return obj, None


def verify(root: str) -> Report:
    r = Report()
    if not os.path.isdir(root):
        r.findings.append(Finding("store-missing", ".", "operator", {}))
        return r
    store = Store(root)

    marker, problem = _read_canonical(store, MARKER)
    if problem == "missing":
        r.state = "foreign"
        r.findings.append(Finding("store-marker", MARKER, "operator", {"problem": problem}))
        return r
    if problem or not (
        isinstance(marker, dict)
        and marker.get("format") == STORE_FORMAT
        and marker.get("format_version") == STORE_FORMAT_VERSION
    ):
        r.findings.append(
            Finding("store-marker", MARKER, "sil", {"problem": problem or "unknown-format"})
        )
        # The store cannot be read as an fsp store; nothing else is trusted.
        return r

    if not store.exists(chain.HEAD):
        r.state = "scaffolded"
        return r
    r.state = "active"

    head, problem = _read_canonical(store, chain.HEAD)
    if problem or not (
        isinstance(head, dict)
        and set(head) == {"entry", "entry_id", "baseline"}
        and isinstance(head["entry"], int)
        and head["entry"] >= 0
    ):
        r.findings.append(Finding("head-invalid", chain.HEAD, "sil", {"problem": problem or "schema"}))
        return r
    n = head["entry"]
    r.head_entry = n
    r.head_digest = head["baseline"]

    chain_ok = _verify_chain(store, head, r)
    content_ok = _verify_content(store, head, r)
    _unclassified(store, r)
    _residue(store, n, r)

    r.chain_intact = chain_ok
    r.content_matches = content_ok
    return r


def _verify_chain(store: Store, head: dict, r: Report) -> bool:
    ok = True
    n = head["entry"]
    prev_id = None
    for k in range(n + 1):
        rel = chain.entry_relpath(k)
        body, problem = _read_canonical(store, rel)
        if problem:
            r.findings.append(Finding("chain-entry", rel, "sil", {"entry": k, "problem": problem}))
            ok = False
            prev_id = None
            continue
        eid = chain.entry_id(body)
        r.entries.append((eid, body))
        r.entry_count += 1
        why = None
        if not isinstance(body, dict) or body.get("entry") != k:
            why = "position"
        elif k == 0:
            if body.get("kind") != "genesis" or "predecessor" in body:
                why = "not-genesis"
            elif not (body.get("binding") and body.get("state_digest") and body.get("version")):
                why = "genesis-fields"
            else:
                r.genesis_digest = eid
        else:
            if body.get("kind") not in ("commit", "version-transition"):
                why = "kind"
            elif prev_id is not None and body.get("predecessor") != prev_id:
                why = "predecessor"
            elif not body.get("state_digest"):
                why = "state-digest"
            elif not body.get("authorization"):
                why = "no-authorization"
        if why:
            r.findings.append(Finding("chain-entry", rel, "sil", {"entry": k, "problem": why}))
            ok = False
        prev_id = eid
        # A history document, when kept, must still hash to its entry.
        if k < n and isinstance(body, dict):
            doc, dproblem = _read_canonical(store, chain.document_relpath(k))
            if dproblem != "missing" and (
                dproblem or document_digest(doc) != body.get("state_digest")
            ):
                r.findings.append(
                    Finding(
                        "integrity-document",
                        chain.document_relpath(k),
                        "sil",
                        {"entry": k, "problem": dproblem or "digest"},
                    )
                )
                ok = False
    if r.entries and len(r.entries) == n + 1:
        last_id, last = r.entries[-1]
        if head["entry_id"] != last_id:
            r.findings.append(Finding("head-mismatch", chain.HEAD, "sil", {"field": "entry_id"}))
            ok = False
        elif head["baseline"] != last.get("state_digest"):
            r.findings.append(Finding("head-mismatch", chain.HEAD, "sil", {"field": "baseline"}))
            ok = False
    return ok


def _verify_content(store: Store, head: dict, r: Report) -> bool:
    n = head["entry"]
    doc_rel = chain.document_relpath(n)
    doc, problem = _read_canonical(store, doc_rel)
    if problem or not isinstance(doc, list):
        r.findings.append(Finding("integrity-document", doc_rel, "sil", {"problem": problem or "schema"}))
        return False
    if document_digest(doc) != head["baseline"]:
        r.findings.append(Finding("integrity-document", doc_rel, "sil", {"problem": "digest"}))
        return False

    gen_rel = chain.gen_relpath(n)
    gen_abs = store.path(gen_rel)
    if not os.path.isdir(gen_abs):
        r.findings.append(Finding("structural-missing", gen_rel, "sil", {}))
        return False
    actual, problems = integrity_document(gen_abs)
    ok = True
    for p in problems:
        r.findings.append(
            Finding(
                "structural-drift",
                gen_rel + "/" + p["path"],
                _owner_of_structural(p["path"]),
                {"problem": p["problem"]},
            )
        )
        ok = False
    expected = {e["path"]: e for e in doc if isinstance(e, dict) and valid_relpath(e.get("path", ""))}
    if len(expected) != len(doc):
        r.findings.append(Finding("integrity-document", doc_rel, "sil", {"problem": "entries"}))
        ok = False
    found = {e["path"]: e for e in actual}
    for path in sorted(set(expected) | set(found)):
        e, a = expected.get(path), found.get(path)
        if e is None:
            problem = "unexpected"
        elif a is None:
            problem = "missing"
        elif a["sha256"] != e["sha256"]:
            problem = "content"
        elif a["exec"] != e["exec"]:
            problem = "exec-bit"
        else:
            continue
        r.findings.append(
            Finding(
                "structural-drift",
                gen_rel + "/" + path,
                _owner_of_structural(path),
                {"problem": problem},
            )
        )
        ok = False
    return ok


_TMP = re.compile(r"^\..+\.tmp-[0-9]+$")


def _unclassified(store: Store, r: Report) -> None:
    """A file that belongs to no content class is not entity state the
    implementation knows how to account for (OC-003(a)(c))."""
    for dirpath, dirnames, filenames in os.walk(store.root):
        rel_dir = os.path.relpath(dirpath, store.root).replace(os.sep, "/")
        if rel_dir.startswith("structural/gen/"):
            dirnames[:] = []  # generations are verified by content above
            continue
        dirnames.sort()
        for name in sorted(filenames):
            rel = name if rel_dir == "." else rel_dir + "/" + name
            if _TMP.match(name):
                r.residue.append({"path": rel, "kind": "temp-file"})
            elif datum_of(rel) is None:
                r.findings.append(Finding("unclassified-datum", rel, "operator", {}))


def _residue(store: Store, n: int, r: Report) -> None:
    for name in store.listdir("integrity/chain"):
        m = re.match(r"^([0-9]{6})\.json$", name)
        if m and int(m.group(1)) > n:
            r.residue.append({"path": "integrity/chain/" + name, "kind": "uncommitted"})
    for name in store.listdir("integrity/documents"):
        m = re.match(r"^([0-9]+)\.json$", name)
        if m and int(m.group(1)) > n:
            r.residue.append({"path": "integrity/documents/" + name, "kind": "uncommitted"})
    for name in store.listdir("structural/gen"):
        if name.isdigit() and int(name) > n:
            r.residue.append({"path": "structural/gen/" + name, "kind": "uncommitted"})
