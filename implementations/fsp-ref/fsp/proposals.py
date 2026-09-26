# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Proposals, approvals and proposal commit (D57, D58)."""

from __future__ import annotations

import posixpath
import re
import secrets

from . import chain, lifecycle, sil
from .digest import canonical, sha256
from .sil import WRITER, Refused, log_append
from .store import INTEGRITY, Store

CATEGORIES = {
    "set-persona": "persona",
    "install-skill": "skills.install",
}

SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


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
        return {"proposals": {}, "approvals": {}}
    data = store.read_json(lifecycle.AUTH)
    if not isinstance(data, dict):
        raise ValueError("authorization state is not an object")
    proposals_obj = data.get("proposals")
    if proposals_obj is not None and not isinstance(proposals_obj, dict):
        raise ValueError("proposals must be an object")
    approvals_obj = data.get("approvals")
    if approvals_obj is not None and not isinstance(approvals_obj, dict):
        raise ValueError("approvals must be an object")
    if "proposals" not in data:
        data["proposals"] = {}
    if "approvals" not in data:
        data["approvals"] = {}
    return data


def write_auth(store: Store, auth: dict) -> None:
    """Write authorization state (lifecycle.AUTH)."""
    store.replace_json(INTEGRITY, lifecycle.AUTH, auth, writer=WRITER)


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

        # Authorization check precedes any content check
        appr = auth.get("approvals", {}).get(proposal_id)
        if appr is None or appr.get("digest") != prop["digest"]:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(b)",
                session=session,
                check="authorization",
                detail="no per-proposal approval and no covering window",
            )
            raise Refused(
                "authorization",
                "OC-001(b)",
                "no per-proposal approval and no covering window",
                [rec],
            )

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

        auth_record = appr["record"]
        out = sil.commit_generation(
            store, changes=changes, authorization=auth_record, session=session
        )

        auth["proposals"].pop(proposal_id, None)
        auth["approvals"].pop(proposal_id, None)
        write_auth(store, auth)

        return {
            "authorization": auth_record,
            "entry": out["entry"],
            "log_records": [out["log_record"]],
        }
