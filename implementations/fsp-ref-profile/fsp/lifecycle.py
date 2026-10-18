# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The SIL's lifecycle: the gated start, the live session, close, revocation,
the passive signal and decommission (DESIGN.md §8).

Every function here runs under the store's write lock, so two starts over
one store serialize and the second sees the first one's credential.
"""

from __future__ import annotations

import json
import os

from . import chain, clock, config, ledger, model, sil, sleep
from . import manifest as skill_manifest
from .digest import canonical
from .sil import WRITER, COMMITTER, Refused, log_append
from .store import INTEGRITY, STRUCTURAL, LockUnavailable, Store
from .verify import store_state, verify

CREDENTIAL = "CREDENTIAL"
SESSIONS = "integrity/sessions.json"
INDEX = "integrity/index.json"
AUTH = "integrity/auth.json"

# (name, token, rule), in the order they run. The passive-signal check is
# first and crash recovery precedes structural verification (OC-010). No
# setting reorders, skips or softens any of them.
GATES = (
    ("passive-signal", "passive", "OC-001(c)"),
    ("crash-recovery", "crash", "OC-010"),
    ("structural-verification", "structural", "OC-004(a)"),
    ("binding-verification", "binding", "OC-001(a)"),
    ("authorization-state", "authorization", "OC-001(b)"),
    ("skill-index", "index", "OC-008(c)"),
)
RULE = {name: rule for name, _token, rule in GATES}


class CannotStart(Exception):
    """No entity to start: absent, foreign or never activated."""


class Holder:
    """The credential's lock, held by the process whose session it is
    (D92). ``release()`` unlocks and closes it, once."""

    def __init__(self, store: Store, fd: int):
        self._store = store
        self._fd = fd

    def release(self):
        fd, self._fd = self._fd, None
        if fd is not None:
            self._store.release_lock(fd)


class StartResult:
    def __init__(self):
        self.outcome = None  # accepted | aborted | refused
        self.gates = []
        self.credential_issued = False
        self.lesser_outcome = None
        self.operator_notified = False
        self.session = None
        self.refusal = None
        self.log_records = []
        self.excluded_skills = []
        self.holder = None

    def gate(self, name, outcome, **extra):
        g = {"gate": name, "outcome": outcome, "rule": RULE[name]}
        g.update(extra)
        self.gates.append(g)

    def detail(self):
        return {
            "gates": self.gates,
            "credential_issued": self.credential_issued,
            "lesser_outcome": self.lesser_outcome,
            "operator_notified": self.operator_notified,
            "session": self.session,
            "excluded_skills": self.excluded_skills,
        }


def _forced_failures(root):
    """Gates a test build was told to fail at this start (``inject
    gate-failure``). Production has no ``fsp_testing``: always empty. The
    hook can make a gate fail; nothing can make one pass."""
    try:
        from fsp_testing import hooks
    except ImportError:
        return frozenset()
    return frozenset(hooks.consume_gate_failures(root))


# -- session state ------------------------------------------------------------

_NO_SESSIONS = {
    "last_session": 0,
    "open_session": None,
    "consecutive_recoveries": 0,
    "ledger_offset": 0,
    "closing": None,
}

PHASES = ("sleep", "endure", "integrity")
MODES = ("normal", "rollover")


def _closing_shape(c):
    """Whether ``c`` is a ``closing`` marker of ``sessions.json`` (D83)."""
    return c is None or (
        isinstance(c, dict)
        and set(c) == {"session", "mode", "done", "ran", "consolidated"}
        and isinstance(c["session"], str)
        and c["mode"] in MODES
        and isinstance(c["done"], list)
        and all(p in PHASES for p in c["done"])
        and len(set(c["done"])) == len(c["done"])
        and isinstance(c["ran"], list)
        and all(p in PHASES for p in c["ran"])
        and len(set(c["ran"])) == len(c["ran"])
        and (c["consolidated"] is None or isinstance(c["consolidated"], dict))
    )


def _read_sessions(store: Store):
    try:
        s = store.read_json(SESSIONS)
    except FileNotFoundError:
        return dict(_NO_SESSIONS)
    if not (
        isinstance(s, dict)
        and set(s) == set(_NO_SESSIONS)
        and isinstance(s["last_session"], int)
        and isinstance(s["consecutive_recoveries"], int)
        and (s["open_session"] is None or isinstance(s["open_session"], str))
        and isinstance(s["ledger_offset"], int)
        and not isinstance(s["ledger_offset"], bool)
        and s["ledger_offset"] >= 0
        and _closing_shape(s["closing"])
    ):
        raise ValueError("session state has the wrong shape")
    return s


def _write_sessions(store: Store, s):
    store.replace_json(INTEGRITY, SESSIONS, s, writer=WRITER)


def _drop_credential(store: Store):
    store.remove(INTEGRITY, CREDENTIAL, writer=WRITER)


def _read_credential(store: Store):
    """The credential's content, ``None`` if absent, ``False`` if unreadable."""
    try:
        cred = store.read_json(CREDENTIAL)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return False
    if not (isinstance(cred, dict) and isinstance(cred.get("session"), str)):
        return False
    return cred


# -- the start (OC-010) ---------------------------------------------------------


def start(root: str, *, binding=None, hold=False) -> StartResult:
    root = os.path.abspath(root)
    state = store_state(root)
    if state != "active":
        raise CannotStart("%s is %s, not an activated entity store" % (root, state))
    store = Store(root)
    forced = _forced_failures(root)
    res = StartResult()
    with store.write_lock():
        acting = binding or sil.owner_binding(store)

        def abort(gate, reason, lesser=None, **evidence):
            res.gate(gate, "fail")
            res.outcome = "aborted"
            res.lesser_outcome = lesser
            res.log_records.append(
                log_append(
                    store,
                    "start-aborted",
                    rule=RULE[gate],
                    binding=acting,
                    gate=gate,
                    reason=reason,
                    **evidence,
                )
            )
            return res

        # 1. passive signal — first, always.
        if store.exists(sil.PASSIVE_SIGNAL):
            return abort("passive-signal", "passive signal present", lesser="suspended")
        if "passive" in forced:
            return abort("passive-signal", "forced by test build", lesser="suspended")
        res.gate("passive-signal", "pass")

        # 2. crash detection and recovery — before structural verification.
        if "crash" in forced:
            return abort("crash-recovery", "forced by test build")
        try:
            sessions = _read_sessions(store)
        except (OSError, ValueError) as e:
            return abort("crash-recovery", "session state unreadable: %s" % e)
        residue = verify(root).residue
        cred = _read_credential(store)
        recover = bool(residue) or sessions["closing"] is not None
        evidence = {"residue": [r["path"] for r in residue]}
        if sessions["closing"] is not None:
            evidence["closing"] = sessions["closing"]["session"]
        if store.exists(CREDENTIAL):
            lock = store.probe_lock(CREDENTIAL) or sil.LOCK_FREE
            holder = cred.get("holder") if isinstance(cred, dict) else None
            process_holder = isinstance(holder, dict) and type(holder.get("pid")) is int
            verdict = sil.classify_credential(
                lock, residue=recover, process_holder=process_holder
            )
            evidence.update(
                {
                    "credential_session": cred.get("session") if cred else None,
                    "lock": lock,
                    "process_holder": process_holder,
                }
            )
            if verdict == "conflict":
                return _conflict(store, res, acting, evidence)
            recover = True
        elif sessions["open_session"]:
            # The credential is gone and nobody closed the session: the
            # Operator removed it directly (OP-021(a)). Record it now.
            res.log_records.append(
                log_append(
                    store,
                    "credential-removed-directly",
                    rule="OC-002(b)",
                    session=sessions["open_session"],
                )
            )
            sessions["open_session"] = None
            _write_sessions(store, sessions)
        if recover:
            attempts = sessions["consecutive_recoveries"]
            if attempts >= config.value(store, "n_boot"):
                rec = sil.raise_passive_signal(
                    store,
                    "recovery-threshold",
                    (
                        "%d consecutive crash recoveries (N_boot); "
                        "halted until the Operator acts"
                    )
                    % attempts,
                )
                res.log_records.append(rec)
                return abort(
                    "crash-recovery",
                    "N_boot reached",
                    lesser="halted",
                    attempts=attempts,
                )
            for item in residue:
                _remove_residue(store, item)
            if store.exists(CREDENTIAL):
                _drop_credential(store)
            sessions["consecutive_recoveries"] = attempts + 1
            sessions["open_session"] = None
            _write_sessions(store, sessions)
            res.log_records.append(
                log_append(
                    store,
                    "recovery",
                    rule="OP-018(a)",
                    binding=acting,
                    attempt=attempts + 1,
                    **evidence,
                )
            )
            outcome = "recovered"
        else:
            outcome = "pass"
        surfaced = _surface_ledger(store, sessions, acting, res)
        extra = {"ledger_surfaced": surfaced} if surfaced else {}
        res.gate("crash-recovery", outcome, **extra)

        # 3. structural verification against the chain.
        if "structural" in forced:
            return abort("structural-verification", "forced by test build")
        report = verify(root)
        if report.log_full_reason in ("checkpoint-missing", "checkpoint-unreadable"):
            res.log_records.append(
                log_append(
                    store,
                    "log-verification",
                    rule="OC-004(a)",
                    binding=acting,
                    mode="full",
                    reason=report.log_full_reason,
                )
            )
        blocking = report.blocking_findings()
        if blocking:
            return abort(
                "structural-verification",
                "structural content does not verify",
                findings=[f.as_dict() for f in blocking],
            )
        if report.decommissioned:
            res.gate("structural-verification", "fail")
            rec = log_append(
                store,
                "refusal",
                rule="OC-002(c)",
                binding=acting,
                check="decommissioned",
                detail="the chain ends in a decommission entry",
            )
            res.outcome = "refused"
            res.refusal = Refused(
                "decommissioned",
                "OC-002(c)",
                "this entity was decommissioned; "
                "its store is a record, not a dormant entity",
                [rec],
            )
            res.log_records.append(rec)
            return res
        res.gate("structural-verification", "pass")

        # 4. binding verification.
        if "binding" in forced:
            return abort("binding-verification", "forced by test build")
        bindings = sil.active_bindings(store)
        if not bindings:
            return abort("binding-verification", "no active Operator binding")
        if acting not in bindings:
            return abort(
                "binding-verification",
                "the starting binding %r is not active" % (acting,),
            )
        owner = sil.owner_binding(store)
        if owner not in bindings:
            return abort(
                "binding-verification",
                "the owner %r is not an active binding" % (owner,),
            )
        res.gate("binding-verification", "pass")

        # 5. authorization state.
        if "authorization" in forced:
            return abort("authorization-state", "forced by test build")
        if store.exists(AUTH):
            try:
                auth = store.read_json(AUTH)
                if not isinstance(auth, dict):
                    raise ValueError("not an object")
            except (OSError, ValueError) as e:
                return abort(
                    "authorization-state", "authorization state unreadable: %s" % e
                )
        from . import proposals

        # D94: a commit a crash interrupted is finished or undone first. D59:
        # expired or exhausted windows close here.
        try:
            res.log_records += proposals.resolve_interrupted(store)
            proposals.close_lapsed(store, clock.grant_now(root))
        except (OSError, ValueError) as e:
            return abort(
                "authorization-state", "authorization state unreadable: %s" % e
            )
        res.gate("authorization-state", "pass")

        # D83: a Closure a crash interrupted resumes at the first phase not
        # done, once the structure and the authorizations it uses are
        # verified.
        if sessions["closing"] is not None:
            out = _run_closure(store, acting, rerun=True)
            res.log_records += out["log_records"]
            sessions = _read_sessions(store)

        # 6. Skill Index build.
        if "index" in forced:
            return abort("skill-index", "forced by test build")
        try:
            index, excluded = _build_index(store, report)
        except (OSError, ValueError) as e:
            return abort("skill-index", "index cannot be built: %s" % e)
        store.replace_json(INTEGRITY, INDEX, index, writer=WRITER)
        if excluded:
            res.excluded_skills = excluded
            res.log_records.append(
                log_append(
                    store,
                    "skill-excluded",
                    rule="OP-006",
                    binding=acting,
                    skills=excluded,
                )
            )
            res.log_records.append(_notify(store, acting, "skill-excluded", excluded))
            res.operator_notified = True
        res.gate("skill-index", "pass", excluded=[e["name"] for e in excluded])

        # Every gate passed: issue the credential (OP-020, D46).
        sessions["last_session"] += 1
        session = "s-%d" % sessions["last_session"]
        cred = {"session": session, "issued_at": clock.iso(), "binding": acting}
        if hold:
            cred["holder"] = {"pid": os.getpid()}
        if not store.create_exclusive(
            INTEGRITY, CREDENTIAL, canonical(cred), writer=WRITER
        ):
            return abort("crash-recovery", "a credential appeared during the start")
        if hold:
            try:
                fd = store.hold_lock(CREDENTIAL)
            except LockUnavailable:
                fd = None
            if fd is None:
                _drop_credential(store)
                return abort("crash-recovery", "credential-lock")
            res.holder = Holder(store, fd)
        sessions["open_session"] = session
        _write_sessions(store, sessions)
        res.log_records.append(
            log_append(
                store,
                "session-open",
                rule="OC-010",
                binding=acting,
                session=session,
                gates=[g["gate"] for g in res.gates],
            )
        )
        from . import mil  # imported here to avoid an import cycle

        mil.open_session_record(store, session, sessions["last_session"])
        in_force = model.setting(store)
        if in_force is not None:
            fp = log_append(
                store,
                "model-fingerprint",
                rule="OC-006",
                binding=acting,
                session=session,
                **in_force,
            )
            res.log_records.append(fp)
            mil.save_session(store, session, "model-fingerprint", record=fp)
        res.outcome = "accepted"
        res.credential_issued = True
        res.session = session
        return res


def _conflict(store, res, acting, evidence):
    """A live session holds the store: refuse, notify the Operator, and
    leave the live session alone (OC-003(d), D49)."""
    res.gate("crash-recovery", "conflict")
    rec = log_append(
        store,
        "refusal",
        rule="OC-003(d)",
        binding=acting,
        check="concurrent-session",
        detail="a live session holds this store",
        **evidence,
    )
    note = _notify(store, acting, "concurrent-session", evidence)
    res.outcome = "refused"
    res.operator_notified = True
    res.refusal = Refused(
        "concurrent-session",
        "OC-003(d)",
        "a session is live over this store (%s); no second credential is issued. "
        "To end it: stop it, or remove %s directly."
        % (evidence.get("credential_session"), CREDENTIAL),
        [rec, note],
    )
    res.log_records += [rec, note]
    return res


def _notify(store, binding, condition, detail):
    """Deliver a notice to the Operator. The channel here is the Operator's
    own invocation — its result and this record; delivery that can fail
    (and falls back to the passive signal, OP-008(b)) comes with the UI."""
    return log_append(
        store,
        "operator-notification",
        rule="OP-008(a)",
        binding=binding,
        condition=condition,
        detail=detail,
    )


def _surface_ledger(store, sessions, acting, res):
    """Surface each Action Ledger entry left open, as a notice, and close it
    ``interrupted`` (OP-015). Returns the ids of the entries surfaced."""
    pending, damaged, end = ledger.unresolved(store, sessions["ledger_offset"])
    for off in damaged:
        rec = _notify(
            store,
            acting,
            "ledger-damaged",
            "the action ledger line at offset %d does not parse" % off,
        )
        res.log_records.append(rec)
    surfaced = []
    for e in pending:
        rec = _notify(
            store,
            acting,
            "ledger-unresolved",
            "%s on %s, entry %s, did not resolve: %s"
            % (e.get("op"), e.get("target"), e.get("id"), e.get("intent")),
        )
        ledger.resolve_entry(store, e["id"], "interrupted", notice=rec)
        res.log_records.append(rec)
        surfaced.append(e["id"])
    if damaged or pending:
        res.operator_notified = True
    sessions["ledger_offset"] = end
    _write_sessions(store, sessions)
    return surfaced


def _remove_residue(store: Store, item):
    path = item["path"]
    if item["kind"] == "temp-file":
        store.remove_temp(path, writer=WRITER)
    elif path.startswith("structural/"):
        store.remove(STRUCTURAL, path, writer=COMMITTER)
    else:
        store.remove(INTEGRITY, path, writer=WRITER)


def _build_index(store: Store, report):
    """The Skill Index of the committed generation. A skill whose files do
    not match the integrity document, or whose manifest does not parse, is
    excluded and reported; the start goes on (OP-006, step 8.8)."""
    n = report.head_entry
    gen = chain.gen_relpath(n)
    drifted = {}
    for f in report.skill_findings():
        parts = f.target.split("/")  # structural/gen/<n>/skills/<name>/...
        if len(parts) > 4:
            drifted.setdefault(parts[4], f.evidence.get("problem"))
    document = store.read_json(chain.document_relpath(n))
    skills, excluded = [], []
    for name in store.listdir(gen + "/skills"):
        if name in drifted:
            excluded.append({"name": name, "reason": "drift: %s" % drifted[name]})
            continue
        try:
            manifest = store.read_json(gen + "/skills/%s/manifest.json" % name)
            found = skill_manifest.problems(manifest, name)
            if found:
                raise ValueError("; ".join(found))
        except (OSError, ValueError) as e:
            excluded.append({"name": name, "reason": "manifest: %s" % e})
            continue
        prefix = "skills/%s/" % name
        skills.append(
            {
                "name": name,
                "files": [
                    {"path": e["path"], "sha256": e["sha256"], "exec": e["exec"]}
                    for e in document
                    if e["path"].startswith(prefix)
                ],
            }
        )
    return {"generation": n, "skills": skills}, excluded


# -- the live session -----------------------------------------------------------


def live_session(root: str):
    """The id of the live session, or None. A session is live while
    ``CREDENTIAL`` exists, is readable and names the session that was opened
    (D46). A credential found missing is recorded here, the first time
    anyone notices."""
    store = Store(root)
    if store_state(store.root) != "active":
        return None
    with store.write_lock():
        try:
            sessions = _read_sessions(store)
        except (OSError, ValueError):
            return None
        cred = _read_credential(store)
        opened = sessions["open_session"]
        if cred and opened and cred["session"] == opened:
            return opened
        if cred is None and opened:
            log_append(
                store, "credential-removed-directly", rule="OC-002(b)", session=opened
            )
            sessions["open_session"] = None
            _write_sessions(store, sessions)
        return None


def require_session(root: str, what: str):
    session = live_session(root)
    if session is None:
        store = Store(root)
        rec = log_append(
            store,
            "refusal",
            rule="OC-002(b)",
            check="no-session",
            detail="%s needs a live session" % what,
        )
        raise Refused(
            "no-session", "OC-002(b)", "%s needs a live session" % what, [rec]
        )
    return session


# -- close, revocation, passive signal, decommission ---------------------------


def stop(root: str, *, binding=None):
    """Normal close, then its Closure (D83, OP-021(a), OP-022). The
    credential is removed in the Integrity phase, after ``closure-complete``,
    and the ``closing`` marker cleared after it."""
    session = require_session(root, "stop")
    store = Store(root)
    with store.write_lock():
        acting = binding or sil.owner_binding(store)
        return close_session(store, session, acting, mode="normal")


def rollover(root: str, *, binding=None):
    """Close the session this process holds for a rollover and run its
    Closure; the caller starts the next session (D94, D9)."""
    session = require_session(root, "rollover")
    store = Store(root)
    with store.write_lock():
        acting = binding or sil.owner_binding(store)
        return close_session(store, session, acting, mode="rollover")


def close_session(store: Store, session, acting, *, mode="normal"):
    """Close ``session`` and run its Closure (D83, D84, D94). Called with the
    write lock held. ``sessions.json`` names the Closure before any record of
    the close is logged."""
    sessions = _read_sessions(store)
    sessions["open_session"] = None
    sessions["consecutive_recoveries"] = 0
    sessions["closing"] = {
        "session": session,
        "mode": mode,
        "done": [],
        "ran": [],
        "consolidated": None,
    }
    _write_sessions(store, sessions)
    close = sil.log_append_located(
        store,
        "session-close",
        rule="OP-021(a)",
        binding=acting,
        session=session,
        mode=mode,
    )
    begin = log_append(
        store, "closure-begin", rule="OP-022(a)", session=session, mode=mode
    )
    out = _run_closure(store, acting)
    return {
        "session": session,
        "log_records": [close["id"], begin] + out["log_records"],
        "sleep": out["sleep"],
        "endure": out["endure"],
        "consolidation": out["consolidation"],
    }


def _endure(store: Store, session):
    """The Endure phase when an authorized proposal waits: ``(result,
    endure-complete record id)``, or ``None`` when none does (D94). Called
    with the write lock held."""
    from . import proposals  # imported here to avoid an import cycle

    if not proposals.waiting(store):
        return None
    result = proposals.endure(store, session)
    record = log_append(
        store,
        "endure-complete",
        rule="OP-022(a)",
        session=session,
        committed=[c["proposal"] for c in result["committed"]],
        dropped=[d["proposal"] for d in result["dropped"]],
    )
    return result, record


def _run_closure(store: Store, acting, *, rerun=False):
    """Run each phase of ``PHASES`` the ``closing`` marker does not list as
    done, in order, and clear the marker last (D83, D94). A phase skipped is
    done like one that ran. Called with the write lock held."""
    from . import mil  # imported here to avoid an import cycle

    sessions = _read_sessions(store)
    closing = sessions["closing"]
    session = closing["session"]
    out = {
        "log_records": [],
        "sleep": {"promoted": [], "refused": []},
        "endure": {"committed": [], "dropped": []},
        "consolidation": None,
    }

    def finish(phase, ran=True):
        closing["done"].append(phase)
        if ran:
            closing["ran"].append(phase)
        _write_sessions(store, sessions)

    if "sleep" not in closing["done"]:
        sleeps = any(
            r.get("kind") in ("closure-payload", "conversation-left")
            for r in mil.session_records(store, session)
        )
        if sleeps:
            slept = sleep.run(store, session, rerun=rerun)
            out["log_records"] += slept["log_records"]
            out["sleep"] = {"promoted": slept["promoted"], "refused": slept["refused"]}
            out["consolidation"] = slept["consolidation"]
            closing["consolidated"] = {
                "closure": slept["closure"],
                "resumption": slept["resumption"],
            }
        finish("sleep", sleeps)

    if "endure" not in closing["done"]:
        endured = _endure(store, session)
        if endured is not None:
            out["endure"], record = endured
            out["log_records"].append(record)
        finish("endure", endured is not None)

    if "integrity" not in closing["done"]:
        consolidated = closing["consolidated"] or {}
        loc = sil.log_append_located(
            store,
            "closure-complete",
            rule="OP-022(a)",
            session=session,
            mode=closing["mode"],
            phases=closing["ran"] + ["integrity"],
            closure=consolidated.get("closure"),
            resumption=consolidated.get("resumption"),
        )
        sil.write_log_checkpoint(store, loc)
        out["log_records"].append(loc["id"])
        finish("integrity", False)
    if store.exists(CREDENTIAL):
        _drop_credential(store)
    sessions["closing"] = None
    _write_sessions(store, sessions)
    return out


def revoke_credential(root: str, *, binding=None):
    """Revocation by the Operator through the implementation."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        cred = _read_credential(store)
        if cred is None:
            rec = log_append(
                store,
                "refusal",
                rule="OC-002(b)",
                binding=acting,
                check="no-session",
                detail="no credential to revoke",
            )
            raise Refused("no-session", "OC-002(b)", "no credential to revoke", [rec])
        rec = sil.operator_act(
            store,
            "revoke-credential",
            binding=acting,
            rule="OC-002(b)",
            session=cred.get("session") if cred else None,
        )
        _drop_credential(store)
        sessions = _read_sessions(store)
        sessions["open_session"] = None
        _write_sessions(store, sessions)
    return {"log_records": [rec]}


def suspend(root: str, *, signal, chain) -> dict:
    """End the session this process holds, without a Closure (D92, D83,
    OP-021(a)): the skills it runs are ended, the session state is cleared,
    the close is logged and the credential removed. A credential another
    process holds is left alone."""
    from . import exec as execution  # imported here to avoid an import cycle

    store = Store(root)
    with store.write_lock():
        cred = _read_credential(store)
        try:
            sessions = _read_sessions(store)
        except (OSError, ValueError):
            sessions = None
        holder = cred.get("holder") if isinstance(cred, dict) else None
        if isinstance(holder, dict) and holder.get("pid") == os.getpid():
            ended = execution.end_running()
            session = cred["session"]
            if sessions is not None:
                sessions["open_session"] = None
                sessions["consecutive_recoveries"] = 0
                _write_sessions(store, sessions)
            binding = cred.get("binding")
            if not isinstance(binding, str):
                binding = sil.owner_binding(store)
            rec = log_append(
                store,
                "session-close",
                rule="OP-021(a)",
                binding=binding,
                session=session,
                mode="suspend",
                signal=signal,
                chain=chain,
                skills_ended=ended,
            )
            _drop_credential(store)
            return {"suspended": True, "session": session, "log_records": [rec]}
        if cred is None and sessions is not None and sessions["open_session"]:
            opened = sessions["open_session"]
            rec = log_append(
                store, "credential-removed-directly", rule="OC-002(b)", session=opened
            )
            sessions["open_session"] = None
            _write_sessions(store, sessions)
            return {"suspended": False, "session": opened, "log_records": [rec]}
        return {"suspended": False, "session": None, "log_records": []}


def clear_passive_signal(root: str, *, binding=None):
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        present = store.exists(sil.PASSIVE_SIGNAL)
        rec = sil.operator_act(
            store,
            "clear-passive-signal",
            binding=acting,
            rule="OC-001(c)",
            detail="passive signal cleared"
            if present
            else "no passive signal was present",
        )
        if present:
            store.remove(INTEGRITY, sil.PASSIVE_SIGNAL, writer=WRITER)
    return {"cleared": present, "log_records": [rec]}


def decommission(root: str, disposition: str, *, binding=None):
    """Close the chain with a terminal entry, then keep the store as an
    archive or destroy it (OP-023, OC-002(c))."""
    from . import proposals  # imported here to avoid an import cycle

    if disposition not in ("archive", "destroy"):
        raise Refused("disposition", "OC-002(c)", "disposition is archive or destroy")
    store = Store(root)
    records = []
    with store.write_lock():
        report = verify(store.root)
        if report.decommissioned:
            rec = log_append(
                store,
                "refusal",
                rule="OC-002(c)",
                check="decommissioned",
                detail="already decommissioned",
            )
            raise Refused(
                "decommissioned", "OC-002(c)", "already decommissioned", [rec]
            )
        if report.findings:
            rec = log_append(
                store,
                "refusal",
                rule="OC-004(a)",
                check="structural",
                detail="the chain cannot be closed over content that does not verify",
            )
            raise Refused(
                "structural",
                "OC-004(a)",
                "the store does not verify; dispose of it directly instead",
                [rec],
            )
        acting = sil.acting_binding(store, binding)
        loc = sil.operator_act_located(
            store,
            "decommission",
            binding=acting,
            rule="OC-002(c)",
            disposition=disposition,
        )
        records.append(loc["id"])
        revoked = None
        if store.exists(CREDENTIAL):
            cred = _read_credential(store)
            revoked = cred["session"] if cred else None
            _drop_credential(store)
            sessions = _read_sessions(store)
            sessions["open_session"] = None
            _write_sessions(store, sessions)
            records.append(
                log_append(
                    store,
                    "credential-revoked",
                    rule="OP-023",
                    binding=acting,
                    reason="decommission",
                )
            )
        records += proposals.resolve_interrupted(store)
        ran = _endure(store, revoked)
        if ran is not None:
            records.append(ran[1])
        out = sil.commit_generation(
            store, changes={}, authorization=loc, kind="decommission"
        )
        records.append(out["log_record"])
        if disposition == "destroy":
            store.destroy(writer=WRITER)
    return {"entry": out["entry"], "disposition": disposition, "log_records": records}


# -- observation ----------------------------------------------------------------


def observe_log(root: str, *, kind=None, since=None):
    """The integrity log's records, after ``since`` and of ``kind``. A line
    that does not decode to a record is skipped and its offset listed in
    ``damaged``, so damage in one line hides none of the others (D45)."""
    store = Store(root)
    try:
        data = store.read_bytes(sil.LOG)
    except FileNotFoundError:
        data = b""
    truncated = bool(data) and not data.endswith(b"\n")
    records, damaged = [], []
    offset = 0
    for line in data.split(b"\n")[:-1]:
        try:
            rec = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            rec = None
        if isinstance(rec, dict):
            records.append(rec)
        else:
            damaged.append(offset)
        offset += len(line) + 1
    if since is not None:
        ids = [r.get("id") for r in records]
        records = records[ids.index(since) + 1 :] if since in ids else []
    if kind is not None:
        records = [r for r in records if r.get("kind") == kind]
    return {"records": records, "truncated_tail": truncated, "damaged": damaged}
