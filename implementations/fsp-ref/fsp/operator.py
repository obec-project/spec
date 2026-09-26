# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Operator acts on bindings and workspace (D28, D30, D48, D55)."""

from __future__ import annotations

import os
from pathlib import Path

from . import lifecycle, proposals, sil
from .sil import Refused, log_append
from .store import Store, canonical
from .verify import verify


def _crosses_boundary(ws: str, limit: str) -> bool:
    """Whether ``ws`` is ``limit``, lies inside it, or contains it, compared by
    path component (D30)."""
    ws_parts = Path(ws).parts
    limit_parts = Path(limit).parts
    n = min(len(ws_parts), len(limit_parts))
    return ws_parts[:n] == limit_parts[:n]


def binding_list(root: str, *, binding=None):
    """The active Operator bindings and owner (D48, D55). Read-only."""
    store = Store(root)
    with store.write_lock():
        active = sil.active_bindings(store)
        if active is None:
            raise Refused("structural", "OC-001(a)", "the binding set cannot be read")
        owner = sil.owner_binding(store)
        return {"bindings": [{"id": b} for b in active], "owner": owner}


def binding_add(root: str, target: str, *, binding=None):
    """Add an Operator binding (OC-001(a), D55). Owner-only, outside session."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        if store.exists(lifecycle.CREDENTIAL):
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="session-live",
                detail="bindings change only outside a session; stop or revoke it first",
            )
            raise Refused(
                "session-live",
                "OC-001(a)",
                "bindings change only outside a session; stop or revoke it first",
                [rec],
            )
        if not (isinstance(target, str) and sil.BINDING_ID.match(target)):
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="binding-id",
                detail="invalid binding id %r" % (target,),
            )
            raise Refused("binding-id", "OC-001(a)", "invalid binding id %r" % (target,), [rec])
        owner = sil.owner_binding(store)
        if acting != owner:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="owner-only",
                detail="only the owner %r can add a binding" % (owner,),
            )
            raise Refused(
                "owner-only",
                "OC-001(a)",
                "only the owner %r can add a binding" % (owner,),
                [rec],
            )
        active = sil.active_bindings(store) or []
        if target in active:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="binding-exists",
                detail="binding %r already exists" % (target,),
            )
            raise Refused(
                "binding-exists",
                "OC-001(a)",
                "binding %r already exists" % (target,),
                [rec],
            )
        report = verify(store.root)
        if report.decommissioned:
            rec = log_append(
                store,
                "refusal",
                rule="OC-002(c)",
                binding=acting,
                check="decommissioned",
                detail="already decommissioned",
            )
            raise Refused("decommissioned", "OC-002(c)", "already decommissioned", [rec])
        if report.findings:
            rec = log_append(
                store,
                "refusal",
                rule="OC-004(a)",
                binding=acting,
                check="structural",
                detail="the store does not verify",
            )
            raise Refused("structural", "OC-004(a)", "the store does not verify", [rec])
        act = sil.operator_act(
            store, "binding-add", binding=acting, rule="OC-001(a)", target=target
        )
        new_bindings = [{"id": b} for b in active] + [{"id": target}]
        new_content = {"bindings": new_bindings, "owner": owner}
        out = sil.commit_generation(
            store,
            changes={"bindings.json": canonical(new_content)},
            authorization=act,
        )
        return {"entry": out["entry"], "log_records": [act, out["log_record"]]}


def binding_remove(root: str, target: str, *, binding=None):
    """Remove an Operator binding (OC-001(a), D55). Outside session."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        if store.exists(lifecycle.CREDENTIAL):
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="session-live",
                detail="bindings change only outside a session; stop or revoke it first",
            )
            raise Refused(
                "session-live",
                "OC-001(a)",
                "bindings change only outside a session; stop or revoke it first",
                [rec],
            )
        if not (isinstance(target, str) and sil.BINDING_ID.match(target)):
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="binding-id",
                detail="invalid binding id %r" % (target,),
            )
            raise Refused("binding-id", "OC-001(a)", "invalid binding id %r" % (target,), [rec])
        active = sil.active_bindings(store) or []
        owner = sil.owner_binding(store)
        if target not in active:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="binding-unknown",
                detail="binding %r is not in the active set" % (target,),
            )
            raise Refused(
                "binding-unknown",
                "OC-001(a)",
                "binding %r is not in the active set" % (target,),
                [rec],
            )
        if len(active) <= 1:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="last-binding",
                detail="cannot remove the last active binding",
            )
            raise Refused(
                "last-binding",
                "OC-001(a)",
                "cannot remove the last active binding",
                [rec],
            )
        if target == owner:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="owner-stays",
                detail="the owner cannot be removed; hand ownership over first",
            )
            raise Refused(
                "owner-stays",
                "OC-001(a)",
                "the owner cannot be removed; hand ownership over first",
                [rec],
            )
        if acting != owner and target != acting:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="owner-only",
                detail="only the owner can remove another binding",
            )
            raise Refused(
                "owner-only",
                "OC-001(a)",
                "only the owner can remove another binding",
                [rec],
            )
        report = verify(store.root)
        if report.decommissioned:
            rec = log_append(
                store,
                "refusal",
                rule="OC-002(c)",
                binding=acting,
                check="decommissioned",
                detail="already decommissioned",
            )
            raise Refused("decommissioned", "OC-002(c)", "already decommissioned", [rec])
        if report.findings:
            rec = log_append(
                store,
                "refusal",
                rule="OC-004(a)",
                binding=acting,
                check="structural",
                detail="the store does not verify",
            )
            raise Refused("structural", "OC-004(a)", "the store does not verify", [rec])
        act = sil.operator_act(
            store, "binding-remove", binding=acting, rule="OC-001(a)", target=target
        )
        new_bindings = [{"id": b} for b in active if b != target]
        new_content = {"bindings": new_bindings, "owner": owner}
        out = sil.commit_generation(
            store,
            changes={"bindings.json": canonical(new_content)},
            authorization=act,
        )
        return {"entry": out["entry"], "log_records": [act, out["log_record"]]}


def set_workspace(root: str, path: str, *, binding=None):
    """Declare the workspace boundary (D28, D30, OC-008(a)(b))."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        ws = os.path.realpath(os.path.abspath(path))
        limits = [
            os.path.realpath(store.root),
            os.path.realpath(os.path.expanduser("~/.fsp")),
        ]
        for limit in limits:
            if _crosses_boundary(ws, limit):
                rec = log_append(
                    store,
                    "refusal",
                    rule="OC-008(b)",
                    binding=acting,
                    check="workspace-boundary",
                    detail="workspace %r crosses boundary %r" % (ws, limit),
                )
                raise Refused(
                    "workspace-boundary",
                    "OC-008(b)",
                    "workspace %r crosses boundary %r" % (ws, limit),
                    [rec],
                )
        act = sil.operator_act(
            store, "set-workspace", binding=acting, rule="OC-008(a)", workspace=ws
        )
        sil.set_operational(store, "workspace", ws)
        return {"workspace": ws, "log_records": [act]}


def approve(root: str, proposal_id: str, *, binding=None):
    """Record an Operator approval for an evolution proposal (OC-001(b), D58)."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        try:
            auth = proposals.read_auth(store)
        except (OSError, ValueError) as e:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(b)",
                binding=acting,
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
                binding=acting,
                check="proposal-unknown",
                detail="proposal %r is not known" % (proposal_id,),
            )
            raise Refused(
                "proposal-unknown",
                "OC-001(b)",
                "proposal %r is not known" % (proposal_id,),
                [rec],
            )
        digest = prop["digest"]
        act = sil.operator_act(
            store, "approve", binding=acting, rule="OC-001(b)", proposal=proposal_id, digest=digest
        )
        proposals.record_approval(store, proposal_id, digest, act, acting)
        return {"log_records": [act]}
