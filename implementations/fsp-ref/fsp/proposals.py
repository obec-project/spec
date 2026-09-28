# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Proposals, approvals and proposal commit (D57, D58)."""

from __future__ import annotations

from datetime import datetime, timedelta
import posixpath
import re
import secrets

from . import chain, clock, lifecycle, sil
from .digest import canonical, sha256
from .sil import WRITER, Refused, log_append
from .store import INTEGRITY, Store

CATEGORIES = {
    "set-persona": "persona",
    "install-skill": "skills.install",
}

WINDOW_CATEGORIES = (
    "skills.install",
    "skills.update",
    "skills.remove",
    "rules",
    "parameters",
)

SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
EXPIRY_RE = re.compile(r"^([+-])(\d+)([smhd])$")


def covers(scope: str, category: str) -> bool:
    return category == scope or category.startswith(scope + ".")


def scope_is_declared(scope: str) -> bool:
    return any(covers(scope, cat) for cat in WINDOW_CATEGORIES)


def parse_expiry(text: str) -> timedelta:
    if not isinstance(text, str):
        raise ValueError("invalid expiry format: expected string")
    m = EXPIRY_RE.match(text)
    if not m:
        raise ValueError("invalid expiry format: %r" % (text,))
    sign_str, num_str, unit = m.groups()
    val = int(num_str)
    units = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }
    seconds = val * units[unit] * (1 if sign_str == "+" else -1)
    return timedelta(seconds=seconds)


def _is_valid_skill_path(p: str) -> bool:
    if not p or p.startswith("/") or "\\" in p:
        return False
    parts = p.split("/")
    if any(comp in ("", ".", "..") for comp in parts):
        return False
    if posixpath.normpath(p) != p:
        return False
    return True


def read_auth(store: Store) -> dict:
    """Read authorization state (lifecycle.AUTH)."""
    if not store.exists(lifecycle.AUTH):
        return {"proposals": {}, "approvals": {}, "grants": []}
    data = store.read_json(lifecycle.AUTH)
    if not isinstance(data, dict):
        raise ValueError("authorization state is not an object")
    proposals_obj = data.get("proposals")
    if proposals_obj is not None and not isinstance(proposals_obj, dict):
        raise ValueError("proposals must be an object")
    approvals_obj = data.get("approvals")
    if approvals_obj is not None and not isinstance(approvals_obj, dict):
        raise ValueError("approvals must be an object")
    grants_obj = data.get("grants")
    if grants_obj is not None and not isinstance(grants_obj, list):
        raise ValueError("grants must be a list")
    if "proposals" not in data:
        data["proposals"] = {}
    if "approvals" not in data:
        data["approvals"] = {}
    if "grants" not in data:
        data["grants"] = []
    return data


def write_auth(store: Store, auth: dict) -> None:
    """Write authorization state (lifecycle.AUTH)."""
    store.replace_json(INTEGRITY, lifecycle.AUTH, auth, writer=WRITER)


def open_window(
    store: Store,
    *,
    scope: str,
    expires: datetime,
    budget: int,
    record: str,
    binding: str,
) -> None:
    """Open an authorization window (D17, D59, OC-001(b))."""
    auth = read_auth(store)
    window = {
        "id": record,
        "scope": scope,
        "expires": clock.iso(expires),
        "budget": budget,
        "used": 0,
        "binding": binding,
        "state": "open",
    }
    auth["grants"].append(window)
    write_auth(store, auth)


def close_lapsed(store: Store, now: datetime, *, session: str = None) -> list[str]:
    """Close open windows that have expired or exhausted their budget (OC-001(b), D59)."""
    auth = read_auth(store)
    closed_ids = []
    now_iso = clock.iso(now)
    for g in auth.get("grants", []):
        if g.get("state") == "open":
            reason = None
            if g.get("expires") and g["expires"] <= now_iso:
                reason = "expired"
            elif g.get("used", 0) >= g.get("budget", 0):
                reason = "exhausted"
            if reason:
                g["state"] = "closed"
                g["closed"] = reason
                log_append(
                    store,
                    "grant-closed",
                    rule="OC-001(b)",
                    session=session,
                    grant=g["id"],
                    reason=reason,
                )
                closed_ids.append(g["id"])
    if closed_ids:
        write_auth(store, auth)
    return closed_ids


def revoke_windows(store: Store, record: str) -> list[str]:
    """Revoke all open authorization windows (OC-001(b), D59)."""
    auth = read_auth(store)
    closed_ids = []
    for g in auth.get("grants", []):
        if g.get("state") == "open":
            g["state"] = "closed"
            g["closed"] = "revoked"
            g["revoked_by"] = record
            closed_ids.append(g["id"])
    if closed_ids:
        write_auth(store, auth)
    return closed_ids


def propose(root: str, ops: list) -> dict:
    """Originate an evolution proposal from ops (D57, D58, OC-001(b))."""
    store = Store(root)
    with store.write_lock():
        # 1. ops is a non-empty list of dicts each with an "op" string
        if not (
            isinstance(ops, list)
            and len(ops) > 0
            and all(isinstance(op, dict) and isinstance(op.get("op"), str) for op in ops)
        ):
            rec = log_append(
                store, "refusal", rule="OC-001(b)", check="ops", detail="invalid ops format"
            )
            raise Refused("ops", "OC-001(b)", "invalid ops format", [rec])

        # 2. binding set cannot be targeted
        if any(op.get("op") in ("add-binding", "remove-binding") for op in ops):
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                check="binding-set",
                detail="a proposal cannot change the Operator binding set",
            )
            raise Refused(
                "binding-set",
                "OC-001(a)",
                "a proposal cannot change the Operator binding set",
                [rec],
            )

        # 3. validate each op
        for op in ops:
            op_name = op["op"]
            if op_name not in CATEGORIES:
                rec = log_append(
                    store,
                    "refusal",
                    rule="OC-001(b)",
                    check="op-unknown",
                    detail="unknown operation %r" % (op_name,),
                )
                raise Refused(
                    "op-unknown",
                    "OC-001(b)",
                    "unknown operation %r" % (op_name,),
                    [rec],
                )
            if op_name == "set-persona":
                content = op.get("content")
                if not isinstance(content, str):
                    rec = log_append(
                        store,
                        "refusal",
                        rule="OC-001(b)",
                        check="ops",
                        detail="set-persona requires a string content",
                    )
                    raise Refused(
                        "ops", "OC-001(b)", "set-persona requires a string content", [rec]
                    )
            elif op_name == "install-skill":
                name = op.get("name")
                if not (isinstance(name, str) and SKILL_NAME.match(name)):
                    rec = log_append(
                        store,
                        "refusal",
                        rule="OC-001(b)",
                        check="ops",
                        detail="install-skill has invalid skill name",
                    )
                    raise Refused(
                        "ops", "OC-001(b)", "install-skill has invalid skill name", [rec]
                    )
                files = op.get("files")
                if not (
                    isinstance(files, dict)
                    and len(files) > 0
                    and all(isinstance(k, str) and isinstance(v, str) for k, v in files.items())
                ):
                    rec = log_append(
                        store,
                        "refusal",
                        rule="OC-001(b)",
                        check="ops",
                        detail="install-skill requires a non-empty files dict of strings",
                    )
                    raise Refused(
                        "ops",
                        "OC-001(b)",
                        "install-skill requires a non-empty files dict of strings",
                        [rec],
                    )
                for file_path in files:
                    if not _is_valid_skill_path(file_path):
                        rec = log_append(
                            store,
                            "refusal",
                            rule="OC-001(b)",
                            check="ops",
                            detail="invalid skill file path %r" % (file_path,),
                        )
                        raise Refused(
                            "ops",
                            "OC-001(b)",
                            "invalid skill file path %r" % (file_path,),
                            [rec],
                        )

        # 4. no duplicate write targets
        targets = set()
        for op in ops:
            op_name = op["op"]
            if op_name == "set-persona":
                target = "persona.md"
                if target in targets:
                    rec = log_append(
                        store,
                        "refusal",
                        rule="OC-001(b)",
                        check="ops",
                        detail="duplicate write target %r" % (target,),
                    )
                    raise Refused(
                        "ops", "OC-001(b)", "duplicate write target %r" % (target,), [rec]
                    )
                targets.add(target)
            elif op_name == "install-skill":
                name = op["name"]
                for file_path in op["files"]:
                    target = "skills/%s/%s" % (name, file_path)
                    if target in targets:
                        rec = log_append(
                            store,
                            "refusal",
                            rule="OC-001(b)",
                            check="ops",
                            detail="duplicate write target %r" % (target,),
                        )
                        raise Refused(
                            "ops", "OC-001(b)", "duplicate write target %r" % (target,), [rec]
                        )
                    targets.add(target)

        # 5. require live session
        session = lifecycle.require_session(root, "propose")

        # 6. read auth state
        try:
            auth = read_auth(store)
        except (OSError, ValueError) as e:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(b)",
                session=session,
                check="authorization-state",
                detail="authorization state unreadable: %s" % (e,),
            )
            raise Refused(
                "authorization-state",
                "OC-001(b)",
                "authorization state unreadable: %s" % (e,),
                [rec],
            )

        # 7. normalize ops
        normalized = []
        for op in ops:
            op_name = op["op"]
            if op_name == "set-persona":
                normalized.append({"op": "set-persona", "content": op["content"]})
            elif op_name == "install-skill":
                normalized.append(
                    {"op": "install-skill", "name": op["name"], "files": dict(op["files"])}
                )

        digest = sha256(canonical(normalized))
        pid = "P-" + secrets.token_hex(8)
        categories = sorted(list(set(CATEGORIES[op["op"]] for op in normalized)))

        # 8. log proposal
        rec = log_append(
            store,
            "proposal",
            rule="OC-001(b)",
            session=session,
            proposal=pid,
            digest=digest,
            categories=categories,
            ops=normalized,
        )

        # 9. save proposal to auth state
        auth["proposals"][pid] = {
            "digest": digest,
            "ops": normalized,
            "record": rec,
            "session": session,
        }
        write_auth(store, auth)

        # 10. return
        return {"proposal": pid, "log_records": [rec]}


def record_approval(store: Store, pid: str, digest: str, record: str, binding: str) -> None:
    """Record an Operator approval for a proposal."""
    auth = read_auth(store)
    auth["approvals"][pid] = {"digest": digest, "record": record, "binding": binding}
    write_auth(store, auth)


def commit(root: str, proposal_id: str) -> dict:
    """Commit an authorized proposal (D57, D58, OC-001(b))."""
    session = lifecycle.require_session(root, "commit")
    store = Store(root)
    with store.write_lock():
        try:
            auth = read_auth(store)
        except (OSError, ValueError) as e:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(b)",
                session=session,
                check="authorization-state",
                detail="authorization state unreadable: %s" % (e,),
            )
            raise Refused(
                "authorization-state",
                "OC-001(b)",
                "authorization state unreadable: %s" % (e,),
                [rec],
            )

        prop = auth.get("proposals", {}).get(proposal_id)
        if prop is None:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(b)",
                session=session,
                check="proposal-unknown",
                detail="proposal %r is not known" % (proposal_id,),
            )
            raise Refused(
                "proposal-unknown",
                "OC-001(b)",
                "proposal %r is not known" % (proposal_id,),
                [rec],
            )

        # Authorization check precedes any content check (D58, D59)
        appr = auth.get("approvals", {}).get(proposal_id)
        covering_grant = None
        auth_record = None

        if appr is not None and appr.get("digest") == prop["digest"]:
            auth_record = appr["record"]
        else:
            now_dt = clock.grant_now(root)
            closed_now = close_lapsed(store, now_dt, session=session)
            if closed_now:
                auth = read_auth(store)

            prop_categories = set(CATEGORIES.get(op.get("op")) for op in prop["ops"])
            can_cover = ("persona" not in prop_categories) and (None not in prop_categories)
            if can_cover:
                for g in auth.get("grants", []):
                    if g.get("state") == "open":
                        scope = g.get("scope", "")
                        if all(covers(scope, cat) for cat in prop_categories):
                            covering_grant = g
                            auth_record = g["id"]
                            break

            if auth_record is None:
                reasons = ["no per-proposal approval"]
                if closed_now:
                    reasons.append("windows closed: %s" % ", ".join(closed_now))
                if "persona" in prop_categories:
                    reasons.append("persona cannot be authorized by a window")
                elif any(g.get("state") == "open" for g in auth.get("grants", [])):
                    reasons.append(
                        "no open window covers categories %s"
                        % sorted(list(prop_categories))
                    )
                else:
                    reasons.append("no open window")
                detail = "; ".join(reasons)
                rec = log_append(
                    store,
                    "refusal",
                    rule="OC-001(b)",
                    session=session,
                    check="authorization",
                    detail=detail,
                )
                raise Refused("authorization", "OC-001(b)", detail, [rec])

        changes = {}
        head = sil.read_head(store)
        existing_skills = set(store.listdir(chain.gen_relpath(head["entry"]) + "/skills"))

        for op in prop["ops"]:
            op_name = op["op"]
            if op_name == "set-persona":
                changes["persona.md"] = op["content"].encode("utf-8")
            elif op_name == "install-skill":
                name = op["name"]
                if name in existing_skills:
                    rec = log_append(
                        store,
                        "refusal",
                        rule="OC-001(b)",
                        session=session,
                        check="skill-exists",
                        detail="skill %r already exists" % (name,),
                    )
                    raise Refused(
                        "skill-exists",
                        "OC-001(b)",
                        "skill %r already exists" % (name,),
                        [rec],
                    )
                for file_path, text in op["files"].items():
                    changes["skills/%s/%s" % (name, file_path)] = text.encode("utf-8")

        out = sil.commit_generation(
            store, changes=changes, authorization=auth_record, session=session
        )

        log_records = [out["log_record"]]
        if covering_grant is not None:
            covering_grant["used"] = covering_grant.get("used", 0) + 1
            if covering_grant["used"] >= covering_grant["budget"]:
                covering_grant["state"] = "closed"
                covering_grant["closed"] = "exhausted"
                rec_closed = log_append(
                    store,
                    "grant-closed",
                    rule="OC-001(b)",
                    session=session,
                    grant=covering_grant["id"],
                    reason="exhausted",
                )
                log_records.append(rec_closed)

        auth["proposals"].pop(proposal_id, None)
        auth["approvals"].pop(proposal_id, None)
        write_auth(store, auth)

        return {
            "authorization": auth_record,
            "entry": out["entry"],
            "log_records": log_records,
        }
