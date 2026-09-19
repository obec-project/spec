"""The SIL's lifecycle: the gated start, the live session, close, revocation,
the passive signal and decommission (DEV-NOTES §12).

Every function here runs under the store's write lock, so two starts over
one store serialize and the second sees the first one's credential.
"""

from __future__ import annotations

import os
import time

from . import chain, clock, config, sil
from .digest import canonical
from .sil import WRITER, COMMITTER, Refused, log_append
from .store import INTEGRITY, STRUCTURAL, Store
from .verify import store_state, verify

CREDENTIAL = "CREDENTIAL"
PULSE = "PULSE"
SESSIONS = "integrity/sessions.json"
INDEX = "integrity/index.json"
AUTH = "integrity/auth.json"

# (name, token, rule), in the order they run. The passive-signal check is
# first and crash recovery precedes structural verification (OC-010). No
# setting reorders, skips or softens any of them.
GATES = (
    ("passive-signal", "passive", "OC-002(c)"),
    ("crash-recovery", "crash", "OC-010"),
    ("structural-verification", "structural", "OC-004(a)"),
    ("binding-verification", "binding", "OC-002(a)"),
    ("authorization-state", "authorization", "OC-002(b)"),
    ("skill-index", "index", "OC-008(c)"),
)
RULE = {name: rule for name, _token, rule in GATES}


class CannotStart(Exception):
    """No entity to start: absent, foreign or never activated."""


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

_NO_SESSIONS = {"last_session": 0, "open_session": None, "consecutive_recoveries": 0}


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
    ):
        raise ValueError("session state has the wrong shape")
    return s


def _write_sessions(store: Store, s):
    store.replace_json(INTEGRITY, SESSIONS, s, writer=WRITER)


def _pulse_fresh(store: Store) -> bool:
    try:
        age = time.time() - os.stat(store.path(PULSE)).st_mtime
    except FileNotFoundError:
        return False
    return age <= config.value(store, "pulse_interval_s")


def _drop_credential(store: Store):
    store.remove(INTEGRITY, CREDENTIAL, writer=WRITER)
    store.remove(INTEGRITY, PULSE, writer=WRITER)


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


def start(root: str, *, binding=None) -> StartResult:
    root = os.path.abspath(root)
    state = store_state(root)
    if state != "active":
        raise CannotStart("%s is %s, not an activated entity store" % (root, state))
    store = Store(root)
    forced = _forced_failures(root)
    res = StartResult()
    with store.write_lock():
        acting = binding or sil.founding_binding(store)

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
        recover = bool(residue)
        evidence = {"residue": [r["path"] for r in residue]}
        if store.exists(CREDENTIAL):
            lock = store.probe_lock(CREDENTIAL) or sil.LOCK_FREE
            fresh = _pulse_fresh(store)
            verdict = sil.classify_credential(lock, residue=bool(residue), pulse_fresh=fresh)
            evidence.update(
                {
                    "credential_session": cred.get("session") if cred else None,
                    "lock": lock,
                    "pulse_fresh": fresh,
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
                    rule="OC-001(b)",
                    session=sessions["open_session"],
                )
            )
            sessions["open_session"] = None
            store.remove(INTEGRITY, PULSE, writer=WRITER)
            _write_sessions(store, sessions)
        if recover:
            attempts = sessions["consecutive_recoveries"]
            if attempts >= config.value(store, "n_boot"):
                rec = sil.raise_passive_signal(
                    store,
                    "recovery-threshold",
                    "%d consecutive crash recoveries (N_boot); halted until the Operator acts" % attempts,
                )
                res.log_records.append(rec)
                return abort("crash-recovery", "N_boot reached", lesser="halted", attempts=attempts)
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
            res.gate("crash-recovery", "recovered")
        else:
            res.gate("crash-recovery", "pass")

        # 3. structural verification against the chain.
        if "structural" in forced:
            return abort("structural-verification", "forced by test build")
        report = verify(root)
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
                rule="OC-001(c)",
                binding=acting,
                check="decommissioned",
                detail="the chain ends in a decommission entry",
            )
            res.outcome = "refused"
            res.refusal = Refused(
                "decommissioned",
                "OC-001(c)",
                "this entity was decommissioned; its store is a record, not a dormant entity",
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
            return abort("binding-verification", "the starting binding %r is not active" % (acting,))
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
                return abort("authorization-state", "authorization state unreadable: %s" % e)
        res.gate("authorization-state", "pass")

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
                log_append(store, "skill-excluded", rule="OP-006", binding=acting, skills=excluded)
            )
            res.log_records.append(_notify(store, acting, "skill-excluded", excluded))
            res.operator_notified = True
        res.gate("skill-index", "pass", excluded=[e["name"] for e in excluded])

        # Every gate passed: issue the credential (OP-020, D46).
        sessions["last_session"] += 1
        session = "s-%d" % sessions["last_session"]
        cred = {"session": session, "issued_at": clock.iso(), "binding": acting}
        if not store.create_exclusive(INTEGRITY, CREDENTIAL, canonical(cred), writer=WRITER):
            return abort("crash-recovery", "a credential appeared during the start")
        store.replace(INTEGRITY, PULSE, (session + "\n").encode("ascii"), writer=WRITER)
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
        "To end it: stop it, or remove %s directly." % (evidence.get("credential_session"), CREDENTIAL),
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
            if not (isinstance(manifest, dict) and manifest.get("name") == name):
                raise ValueError("manifest does not name the skill")
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
    (D46). Acting within it refreshes the ``PULSE`` (D47). A credential
    found missing is recorded here, the first time anyone notices."""
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
            if store.exists(PULSE):
                store.touch(INTEGRITY, PULSE, writer=WRITER)
            else:
                store.replace(INTEGRITY, PULSE, (opened + "\n").encode("ascii"), writer=WRITER)
            return opened
        if cred is None and opened:
            log_append(store, "credential-removed-directly", rule="OC-001(b)", session=opened)
            sessions["open_session"] = None
            _write_sessions(store, sessions)
            store.remove(INTEGRITY, PULSE, writer=WRITER)
        return None


def require_session(root: str, what: str):
    session = live_session(root)
    if session is None:
        store = Store(root)
        rec = log_append(
            store,
            "refusal",
            rule="OC-001(b)",
            check="no-session",
            detail="%s needs a live session" % what,
        )
        raise Refused("no-session", "OC-001(b)", "%s needs a live session" % what, [rec])
    return session


# -- close, revocation, passive signal, decommission ---------------------------


def stop(root: str, *, binding=None):
    """Normal close. Sleep and the Closure Payload come with memory (Phase 7)."""
    session = require_session(root, "stop")
    store = Store(root)
    with store.write_lock():
        acting = binding or sil.founding_binding(store)
        _drop_credential(store)
        sessions = _read_sessions(store)
        sessions["open_session"] = None
        sessions["consecutive_recoveries"] = 0
        _write_sessions(store, sessions)
        rec = log_append(
            store, "session-close", rule="OP-021(a)", binding=acting, session=session, mode="normal"
        )
    return {"session": session, "log_records": [rec]}


def revoke_credential(root: str, *, binding=None):
    """Revocation by the Operator through the implementation."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        cred = _read_credential(store)
        if cred is None:
            rec = log_append(
                store, "refusal", rule="OC-001(b)", binding=acting, check="no-session",
                detail="no credential to revoke",
            )
            raise Refused("no-session", "OC-001(b)", "no credential to revoke", [rec])
        rec = sil.operator_act(
            store,
            "revoke-credential",
            binding=acting,
            rule="OC-001(b)",
            session=cred.get("session") if cred else None,
        )
        _drop_credential(store)
        sessions = _read_sessions(store)
        sessions["open_session"] = None
        _write_sessions(store, sessions)
    return {"log_records": [rec]}


def clear_passive_signal(root: str, *, binding=None):
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        present = store.exists(sil.PASSIVE_SIGNAL)
        rec = sil.operator_act(
            store,
            "clear-passive-signal",
            binding=acting,
            rule="OC-002(c)",
            detail="passive signal cleared" if present else "no passive signal was present",
        )
        if present:
            store.remove(INTEGRITY, sil.PASSIVE_SIGNAL, writer=WRITER)
    return {"cleared": present, "log_records": [rec]}


def decommission(root: str, disposition: str, *, binding=None):
    """Close the chain with a terminal entry, then keep the store as an
    archive or destroy it (OP-023, OC-001(c))."""
    if disposition not in ("archive", "destroy"):
        raise Refused("disposition", "OC-001(c)", "disposition is archive or destroy")
    store = Store(root)
    records = []
    with store.write_lock():
        report = verify(store.root)
        if report.decommissioned:
            rec = log_append(
                store, "refusal", rule="OC-001(c)", check="decommissioned",
                detail="already decommissioned",
            )
            raise Refused("decommissioned", "OC-001(c)", "already decommissioned", [rec])
        if report.findings:
            rec = log_append(
                store, "refusal", rule="OC-004(a)", check="structural",
                detail="the chain cannot be closed over content that does not verify",
            )
            raise Refused(
                "structural", "OC-004(a)",
                "the store does not verify; dispose of it directly instead", [rec],
            )
        acting = sil.acting_binding(store, binding)
        act = sil.operator_act(
            store, "decommission", binding=acting, rule="OC-001(c)", disposition=disposition
        )
        records.append(act)
        if store.exists(CREDENTIAL):
            _drop_credential(store)
            sessions = _read_sessions(store)
            sessions["open_session"] = None
            _write_sessions(store, sessions)
            records.append(
                log_append(store, "credential-revoked", rule="OP-023", binding=acting, reason="decommission")
            )
        out = sil.commit_generation(store, changes={}, authorization=act, kind="decommission")
        records.append(out["log_record"])
        if disposition == "destroy":
            store.destroy(writer=WRITER)
    return {"entry": out["entry"], "disposition": disposition, "log_records": records}


# -- observation ----------------------------------------------------------------


def observe_log(root: str, *, kind=None, since=None):
    store = Store(root)
    records, truncated = store.read_jsonl(sil.LOG)
    if since is not None:
        ids = [r.get("id") for r in records]
        records = records[ids.index(since) + 1 :] if since in ids else []
    if kind is not None:
        records = [r for r in records if r.get("kind") == kind]
    return {"records": records, "truncated_tail": truncated}
