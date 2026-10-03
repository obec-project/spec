# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Operator acts on bindings, ownership handover, and workspace (D28, D30, D48, D55)."""

from __future__ import annotations

import os
from pathlib import Path

from . import clock, lifecycle, proposals, sil
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
        loc = sil.operator_act_located(
            store, "binding-add", binding=acting, rule="OC-001(a)", target=target
        )
        new_bindings = [{"id": b} for b in active] + [{"id": target}]
        new_content = {"bindings": new_bindings, "owner": owner}
        out = sil.commit_generation(
            store,
            changes={"bindings.json": canonical(new_content)},
            authorization=loc,
        )
        return {"entry": out["entry"], "log_records": [loc["id"], out["log_record"]]}


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
        loc = sil.operator_act_located(
            store, "binding-remove", binding=acting, rule="OC-001(a)", target=target
        )
        new_bindings = [{"id": b} for b in active if b != target]
        new_content = {"bindings": new_bindings, "owner": owner}
        out = sil.commit_generation(
            store,
            changes={"bindings.json": canonical(new_content)},
            authorization=loc,
        )
        auth = proposals.read_auth(store)
        offer = auth.get("ownership_offer")
        if offer and offer.get("to") == target:
            auth.pop("ownership_offer", None)
            proposals.write_auth(store, auth)
        return {"entry": out["entry"], "log_records": [loc["id"], out["log_record"]]}


def ownership_offer(root: str, target: str, *, binding=None):
    """Offer ownership of the Operator binding set to another active binding (OC-001(a), D55)."""
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
                detail="only the owner can offer ownership",
            )
            raise Refused("owner-only", "OC-001(a)", "only the owner can offer ownership", [rec])
        if target == owner:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="ownership-self",
                detail="cannot offer ownership to oneself",
            )
            raise Refused(
                "ownership-self", "OC-001(a)", "cannot offer ownership to oneself", [rec]
            )
        active = sil.active_bindings(store) or []
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
        loc = sil.operator_act_located(
            store, "ownership-offer", binding=acting, rule="OC-001(a)", target=target
        )
        auth = proposals.read_auth(store)
        auth["ownership_offer"] = {"to": target, "record": loc["id"], "binding": acting}
        proposals.write_auth(store, auth)
        return {"offer": target, "log_records": [loc["id"]]}


def ownership_accept(root: str, *, binding=None):
    """Accept an ownership offer and commit the new owner (OC-001(a), D55)."""
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
        auth = proposals.read_auth(store)
        offer = auth.get("ownership_offer")
        if not offer:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="no-offer",
                detail="there is no pending ownership offer",
            )
            raise Refused(
                "no-offer", "OC-001(a)", "there is no pending ownership offer", [rec]
            )
        if offer.get("to") != acting:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="not-offered",
                detail="ownership was not offered to %r" % (acting,),
            )
            raise Refused(
                "not-offered",
                "OC-001(a)",
                "ownership was not offered to %r" % (acting,),
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
        loc = sil.operator_act_located(
            store, "ownership-accept", binding=acting, rule="OC-001(a)", offer=offer["record"]
        )
        active = sil.active_bindings(store) or []
        new_content = {"bindings": [{"id": b} for b in active], "owner": acting}
        out = sil.commit_generation(
            store,
            changes={"bindings.json": canonical(new_content)},
            authorization=loc,
        )
        auth = proposals.read_auth(store)
        auth.pop("ownership_offer", None)
        proposals.write_auth(store, auth)
        return {"entry": out["entry"], "owner": acting, "log_records": [loc["id"], out["log_record"]]}


def ownership_withdraw(root: str, *, binding=None):
    """Withdraw a pending ownership offer (OC-001(a), D55). Owner-only, outside session."""
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
        owner = sil.owner_binding(store)
        if acting != owner:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="owner-only",
                detail="only the owner can withdraw an ownership offer",
            )
            raise Refused(
                "owner-only", "OC-001(a)", "only the owner can withdraw an ownership offer", [rec]
            )
        auth = proposals.read_auth(store)
        offer = auth.get("ownership_offer")
        if not offer:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="no-offer",
                detail="there is no pending ownership offer",
            )
            raise Refused(
                "no-offer", "OC-001(a)", "there is no pending ownership offer", [rec]
            )
        loc = sil.operator_act_located(
            store, "ownership-withdraw", binding=acting, rule="OC-001(a)", offer=offer["record"]
        )
        auth.pop("ownership_offer", None)
        proposals.write_auth(store, auth)
        return {"log_records": [loc["id"]]}


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
        loc = sil.operator_act_located(
            store, "approve", binding=acting, rule="OC-001(b)", proposal=proposal_id, digest=digest
        )
        proposals.record_approval(store, proposal_id, digest, loc["id"], acting, authorization=loc)
        return {"log_records": [loc["id"]]}


def grant(root: str, *, expiry=None, budget=None, scope=None, binding=None):
    """Open an authorization window (D17, D59, OC-001(b))."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)

        for axis_name, axis_val in (("expiry", expiry), ("budget", budget), ("scope", scope)):
            if axis_val is None or axis_val == "":
                detail = "a window is bounded on all three axes: --%s is missing" % (axis_name,)
                rec = log_append(
                    store,
                    "refusal",
                    rule="OC-001(b)",
                    binding=acting,
                    check="grant-unbounded",
                    detail=detail,
                )
                raise Refused("grant-unbounded", "OC-001(b)", detail, [rec])

        if scope in ("binding-set", "bindings"):
            detail = "no window may cover the Operator binding set"
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="scope",
                detail=detail,
            )
            raise Refused("scope", "OC-001(a)", detail, [rec])

        if not proposals.scope_is_declared(scope):
            detail = "scope %r is not declared; declared window categories are %s" % (
                scope,
                ", ".join(proposals.WINDOW_CATEGORIES),
            )
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(b)",
                binding=acting,
                check="scope",
                detail=detail,
            )
            raise Refused("scope", "OC-001(b)", detail, [rec])

        budget_int = None
        if isinstance(budget, int) and not isinstance(budget, bool):
            budget_int = budget
        elif isinstance(budget, str) and budget.isascii() and budget.isdigit():
            budget_int = int(budget)
        if budget_int is None or budget_int < 1:
            detail = "budget must be an integer >= 1, got %r" % (budget,)
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(b)",
                binding=acting,
                check="grant-budget",
                detail=detail,
            )
            raise Refused("grant-budget", "OC-001(b)", detail, [rec])

        try:
            delta = proposals.parse_expiry(expiry)
        except ValueError as e:
            detail = "invalid expiry: %s" % (e,)
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(b)",
                binding=acting,
                check="grant-expiry",
                detail=detail,
            )
            raise Refused("grant-expiry", "OC-001(b)", detail, [rec])

        try:
            proposals.read_auth(store)
        except (OSError, ValueError) as e:
            detail = "authorization state unreadable: %s" % (e,)
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(b)",
                binding=acting,
                check="authorization-state",
                detail=detail,
            )
            raise Refused("authorization-state", "OC-001(b)", detail, [rec])

        expires = clock.grant_now(root) + delta

        loc = sil.operator_act_located(
            store,
            "grant",
            binding=acting,
            rule="OC-001(b)",
            scope=scope,
            budget=budget_int,
            expires=clock.iso(expires),
        )
        proposals.open_window(
            store,
            scope=scope,
            expires=expires,
            budget=budget_int,
            record=loc["id"],
            binding=acting,
            authorization=loc,
        )

        return {"grant": loc["id"], "log_records": [loc["id"]]}


def revoke_grant(root: str, *, binding=None):
    """Revoke all open authorization windows (OC-001(b), D59)."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        try:
            proposals.read_auth(store)
        except (OSError, ValueError) as e:
            detail = "authorization state unreadable: %s" % (e,)
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(b)",
                binding=acting,
                check="authorization-state",
                detail=detail,
            )
            raise Refused(
                "authorization-state",
                "OC-001(b)",
                detail,
                [rec],
            )
        act = sil.operator_act(store, "revoke-grant", binding=acting, rule="OC-001(b)")
        closed = proposals.revoke_windows(store, act)
        return {"revoked": closed, "log_records": [act]}
