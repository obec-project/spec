# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Vital Check before an act of the entity (D65).

The check does not run on a timer. Before each act of the entity in a live
session, ``before_act`` looks at the state of the check: when it is due —
``vital_interval_s`` seconds since the last one, or ``vital_activity_n`` acts
since it — ``check`` runs ``verify`` twice (a finding must survive the second
read to count, OP-003(b)). A confirmed finding owned by ``exec`` is corrected
by pruning its skill from the Skill Index, up to ``n_corrections`` attempts
(D40); any other confirmed finding, or an uncorrected one, is Critical: the
credential is revoked, the session closed, and the passive signal written
(D66). Operator acts neither count nor trigger a check.

Each check also scans one block of the integrity log (D45 (3)), from the
position the previous check left in the state. A finding of that scan must
survive a second read, as above; a confirmed one is Critical.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import clock, config, lifecycle, sil
from .sil import Refused, log_append
from .store import INTEGRITY, Store
from .verify import sweep_log, verify

STATE = "integrity/vital.json"
SWEEP_BLOCK = 1 << 20


def _default_state():
    return {"session": None, "last_check": None, "acts_since": 0, "sweep": {"log": None}}


def _read_state(store: Store):
    try:
        state = store.read_json(STATE)
    except (OSError, ValueError):
        return _default_state()
    if not (
        isinstance(state, dict)
        and set(state) == {"session", "last_check", "acts_since", "sweep"}
        and (state["session"] is None or isinstance(state["session"], str))
        and (state["last_check"] is None or isinstance(state["last_check"], str))
        and isinstance(state["acts_since"], int)
        and not isinstance(state["acts_since"], bool)
        and state["acts_since"] >= 0
        and isinstance(state["sweep"], dict)
    ):
        return _default_state()
    return state


def _write_state(store: Store, state):
    store.replace_json(INTEGRITY, STATE, state, writer=sil.WRITER)


def _parse(text):
    if not isinstance(text, str):
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def before_act(root: str, session: str):
    """Run the Vital Check before an act of the entity if one is due (D65).

    Returns ``None`` when no check is due, ``"nominal"`` or ``"degraded"``
    when one ran, and raises ``Refused`` on a Critical finding (D66)."""
    store = Store(root)
    with store.write_lock():
        state = _read_state(store)
        now = clock.grant_now(root)
        if state["session"] != session:
            # The start that opened this session verified the store already.
            cred = lifecycle._read_credential(store)
            issued = cred.get("issued_at") if isinstance(cred, dict) else None
            if _parse(issued) is None:
                issued = clock.iso(now)
            state = {
                "session": session,
                "last_check": issued,
                "acts_since": 0,
                "sweep": state["sweep"],
            }
        acts = state["acts_since"] + 1
        last = _parse(state["last_check"])
        due = (
            last is None
            or (now - last).total_seconds() >= config.value(store, "vital_interval_s")
            or acts >= config.value(store, "vital_activity_n")
        )
        if not due:
            state["acts_since"] = acts
            _write_state(store, state)
            return None
        result = check(store, root, session)
        _sweep(store, session, state)
        state["last_check"] = clock.iso(now)
        state["acts_since"] = 0
        _write_state(store, state)
        return result


def _sweep(store: Store, session, state):
    """Scan the next block of the integrity log (D45 (3)). A finding is
    confirmed by a second read (D40); a confirmed one is Critical."""
    sweep = state["sweep"]
    position = sweep.get("log")
    finding, new_position, reset = sweep_log(store, position, SWEEP_BLOCK)
    if reset is not None:
        log_append(
            store,
            "vital-sweep-reset",
            rule="OP-003(b)",
            session=session,
            file="integrity/log.jsonl",
            reason=reset,
        )
    if finding is not None:
        again, _, _ = sweep_log(store, position, SWEEP_BLOCK)
        if again is None or (again.type, again.target, again.evidence.get("offset")) != (
            finding.type,
            finding.target,
            finding.evidence.get("offset"),
        ):
            log_append(
                store,
                "vital-noise",
                rule="OP-003(b)",
                session=session,
                findings=[finding.as_dict()],
            )
            return
        _critical(store, session, [finding])
    sweep["log"] = new_position


def check(store: Store, root: str, session: str):
    """Confirm the findings of two reads and act on the confirmed ones (D40,
    OP-003(b)). Returns ``"nominal"`` or ``"degraded"``, or raises ``Refused``."""
    first = verify(root)
    if not first.findings:
        return "nominal"
    second = verify(root)
    second_keys = {(f.type, f.target) for f in second.findings}
    first_keys = {(f.type, f.target) for f in first.findings}
    noise = [f for f in first.findings if (f.type, f.target) not in second_keys]
    if noise:
        log_append(
            store,
            "vital-noise",
            rule="OP-003(b)",
            session=session,
            findings=[f.as_dict() for f in noise],
        )
    confirmed = [f for f in second.findings if (f.type, f.target) in first_keys]
    if not confirmed:
        return "nominal"
    structural = [f for f in confirmed if f.owner != "exec"]
    if structural:
        _critical(store, session, structural)
    return _correct_skills(store, second, session, confirmed)


def _skill_of(f):
    """The skill a finding names: ``structural/gen/<n>/skills/<name>/...``."""
    parts = f.target.split("/")
    return parts[4] if len(parts) > 4 else None


def _correct_skills(store: Store, report, session, findings):
    """Prune the skills named by ``findings`` from the Skill Index (OP-006),
    retrying up to ``n_corrections`` times, then escalate (D40)."""
    try:
        indexed = {s["name"] for s in store.read_json(lifecycle.INDEX)["skills"]}
    except (OSError, ValueError, KeyError, TypeError):
        indexed = set()
    to_prune = {_skill_of(f) for f in findings} & indexed
    if not to_prune:
        return "nominal"
    for f in findings:
        if _skill_of(f) in to_prune:
            log_append(store, "anomaly", rule="OP-003(b)", session=session, **f.as_dict())
    for attempt in range(1, config.value(store, "n_corrections") + 1):
        index, excluded = lifecycle._build_index(store, report)
        store.replace_json(INTEGRITY, lifecycle.INDEX, index, writer=sil.WRITER)
        log_append(
            store,
            "corrected",
            rule="OP-003(b)",
            session=session,
            action="skill-pruned",
            skills=sorted(to_prune),
            attempt=attempt,
        )
        remaining = {s["name"] for s in store.read_json(lifecycle.INDEX)["skills"]}
        if not (to_prune & remaining):
            log_append(store, "skill-excluded", rule="OP-006", session=session, skills=excluded)
            cred = lifecycle._read_credential(store)
            binding = cred.get("binding") if isinstance(cred, dict) else None
            lifecycle._notify(store, binding, "skill-excluded", excluded)
            return "degraded"
    _critical(store, session, findings)


def _critical(store: Store, session, findings):
    """Revoke the credential, close the session, write the passive signal, and
    refuse (OP-003(b), D46, D66). Always raises ``Refused``."""
    detail = "; ".join("%s %s" % (f.type, f.target) for f in findings)
    cred = lifecycle._read_credential(store)
    binding = cred.get("binding") if isinstance(cred, dict) else None
    records = []
    records.append(
        log_append(
            store,
            "vital-critical",
            rule="OP-003(b)",
            session=session,
            findings=[f.as_dict() for f in findings],
        )
    )
    if store.exists(lifecycle.CREDENTIAL):
        lifecycle._drop_credential(store)
        records.append(
            log_append(
                store,
                "credential-revoked",
                rule="OP-003(b)",
                session=session,
                reason="vital-critical",
            )
        )
    try:
        sessions = lifecycle._read_sessions(store)
        sessions["open_session"] = None
        lifecycle._write_sessions(store, sessions)
    except (OSError, ValueError):
        pass
    records.append(lifecycle._notify(store, binding, "vital-critical", detail))
    records.append(sil.raise_passive_signal(store, "vital-critical", detail, session=session))
    raise Refused("vital-critical", "OP-003(b)", detail, records)


def require_entity_session(root: str, what: str):
    """``require_session`` for an act of the entity, which runs the Vital
    Check before it when one is due (D65)."""
    session = lifecycle.require_session(root, what)
    before_act(root, session)
    return session
