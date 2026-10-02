# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Verification of committed structural content against the chain (OC-004(a)).

One function serves the start gate, ``lifecycle verify`` and, later, the
Vital Check (D37). It never repairs anything: it returns **findings**, each
``{type, target, owner, evidence}``, and the caller decides. ``owner`` is the
component whose authority covers the correction (DESIGN.md §6.7).

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
from .digest import canonical, document_digest, integrity_document, sha256, valid_relpath
from .store import LOCK, MARKER, STORE_FORMAT, STORE_FORMAT_VERSION, TEMP_NAME, Store, datum_of


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
        self.decommissioned = False
        self.log_mode = None
        self.log_full_reason = None

    @property
    def verified(self):
        return self.state == "active" and not self.findings

    def skill_findings(self):
        """Findings the execution path corrects by pruning the skill from
        the index (OP-006) — they do not stop a start (step 8.8)."""
        return [f for f in self.findings if f.owner == "exec"]

    def blocking_findings(self):
        return [f for f in self.findings if f.owner != "exec"]

    def as_dict(self):
        return {
            "state": self.state,
            "decommissioned": self.decommissioned,
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


def store_state(root: str) -> str:
    """``absent``, ``foreign`` (not an fsp store), ``scaffolded`` (no
    ``HEAD`` yet) or ``active``. Cheap: no hashing."""
    if not os.path.isdir(root):
        return "absent"
    if not os.path.lexists(os.path.join(root, MARKER)):
        return "foreign"
    if not os.path.lexists(os.path.join(root, chain.HEAD)):
        return "scaffolded"
    return "active"


def verify(root: str, *, full_log: bool = False) -> Report:
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
    log_ok = _verify_log(store, r, full_log=full_log)
    content_ok = _verify_content(store, head, r)
    _unclassified(store, r)
    _residue(store, n, r)

    r.chain_intact = chain_ok and log_ok
    r.content_matches = content_ok
    return r


def _verify_chain(store: Store, head: dict, r: Report) -> bool:
    ok = True
    n = head["entry"]
    prev_id = None
    prev_kind = None
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
            if body.get("kind") not in chain.COMMIT_KINDS:
                why = "kind"
            elif prev_kind == "decommission":
                why = "after-decommission"
            elif prev_id is not None and body.get("predecessor") != prev_id:
                why = "predecessor"
            elif not body.get("state_digest"):
                why = "state-digest"
            elif not authorization_resolves(store, body):
                why = "authorization-unresolved"
        if why:
            r.findings.append(Finding("chain-entry", rel, "sil", {"entry": k, "problem": why}))
            ok = False
        prev_id = eid
        prev_kind = body.get("kind") if isinstance(body, dict) else None
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
        elif ok and last.get("kind") == "decommission":
            r.decommissioned = True
    return ok


def authorization_resolves(store: Store, body: dict) -> bool:
    """Resolve an entry's authorization against the log (D45 (1))."""
    auth = body.get("authorization")
    if not isinstance(auth, dict) or set(auth.keys()) != {"id", "sha256", "offset"}:
        return False
    auth_id = auth.get("id")
    auth_sha256 = auth.get("sha256")
    auth_offset = auth.get("offset")
    if not isinstance(auth_id, str) or not re.match(r"^L-[0-9]{6}$", auth_id):
        return False
    if not isinstance(auth_offset, int) or isinstance(auth_offset, bool) or auth_offset < 0:
        return False
    if not isinstance(auth_sha256, str):
        return False

    line = store.read_line_at("integrity/log.jsonl", auth_offset)
    if line is None or sha256(line) != auth_sha256:
        return False

    try:
        rec = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False
    if not isinstance(rec, dict) or rec.get("id") != auth_id or rec.get("kind") != "operator-act":
        return False

    entry_kind = body.get("kind")
    act = rec.get("act")
    if entry_kind == "commit":
        return act in {"approve", "grant", "binding-add", "binding-remove"}
    elif entry_kind == "decommission":
        return act == "decommission"
    return False


def _verify_log(store: Store, r: Report, *, full_log: bool = False) -> bool:
    """Verify integrity log: tail from checkpoint or full log (D45 (2)(3))."""
    if not store.exists("integrity/log.jsonl"):
        r.findings.append(
            Finding("log-record", "integrity/log.jsonl", "sil", {"problem": "missing"})
        )
        return False

    start_offset = 0
    expected_seq = 1
    expected_prev = None

    if full_log:
        r.log_mode = "full"
        r.log_full_reason = "requested"
    else:
        chk, problem = _read_canonical(store, "integrity/log-checkpoint.json")
        if problem == "missing":
            r.log_mode = "full"
            r.log_full_reason = "checkpoint-missing"
        elif (
            problem is not None
            or not isinstance(chk, dict)
            or set(chk.keys()) != {"id", "sha256", "offset"}
            or not isinstance(chk.get("id"), str)
            or not re.match(r"^L-[0-9]{6}$", chk["id"])
            or not isinstance(chk.get("offset"), int)
            or isinstance(chk.get("offset"), bool)
            or chk["offset"] < 0
            or not isinstance(chk.get("sha256"), str)
        ):
            r.log_mode = "full"
            r.log_full_reason = "checkpoint-unreadable"
        else:
            line = store.read_line_at("integrity/log.jsonl", chk["offset"])
            resolved = False
            chk_rec = None
            if line is not None and sha256(line) == chk["sha256"]:
                try:
                    rec = json.loads(line.decode("utf-8"))
                    if isinstance(rec, dict) and rec.get("id") == chk["id"]:
                        resolved = True
                        chk_rec = rec
                except (UnicodeDecodeError, ValueError):
                    pass
            if not resolved:
                r.findings.append(
                    Finding(
                        "log-checkpoint",
                        "integrity/log-checkpoint.json",
                        "sil",
                        {"problem": "mismatch"},
                    )
                )
                return False

            r.log_mode = "tail"
            r.log_full_reason = None
            start_offset = chk["offset"] + len(line) + 1
            expected_seq = int(chk_rec["id"].split("-")[1]) + 1
            expected_prev = sha256(line)

    data = store.read_from("integrity/log.jsonl", start_offset)
    lines = data.split(b"\n")
    complete_lines = lines[:-1]
    cur_offset = start_offset

    for line in complete_lines:
        try:
            rec = json.loads(line.decode("utf-8"))
            if not isinstance(rec, dict):
                raise ValueError("not a dict")
        except (UnicodeDecodeError, ValueError):
            r.findings.append(
                Finding(
                    "log-record",
                    "integrity/log.jsonl",
                    "sil",
                    {"offset": cur_offset, "problem": "unparseable"},
                )
            )
            return False

        if canonical(rec) != line:
            r.findings.append(
                Finding(
                    "log-record",
                    "integrity/log.jsonl",
                    "sil",
                    {"offset": cur_offset, "problem": "not-canonical"},
                )
            )
            return False

        expected_id = "L-%06d" % expected_seq
        if rec.get("id") != expected_id:
            r.findings.append(
                Finding(
                    "log-record",
                    "integrity/log.jsonl",
                    "sil",
                    {"offset": cur_offset, "problem": "sequence"},
                )
            )
            return False

        if rec.get("prev") != expected_prev:
            r.findings.append(
                Finding(
                    "log-record",
                    "integrity/log.jsonl",
                    "sil",
                    {"offset": cur_offset, "problem": "prev"},
                )
            )
            return False

        expected_seq += 1
        expected_prev = sha256(line)
        cur_offset += len(line) + 1

    return True


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
            if TEMP_NAME.match(name):
                r.residue.append({"path": rel, "kind": "temp-file"})
            elif datum_of(rel) is None:
                r.findings.append(Finding("unclassified-datum", rel, "operator", {}))
            elif rel == LOCK and os.path.getsize(os.path.join(dirpath, name)):
                # The lock file carries no content; bytes in it are not ours.
                r.findings.append(Finding("store-lock", rel, "sil", {"problem": "not-empty"}))


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
