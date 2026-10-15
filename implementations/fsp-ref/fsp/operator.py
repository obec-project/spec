# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Operator acts on bindings, ownership handover, workspace, and operator
notices (D28, D30, D48, D55, D66)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import clock, config, cycle, lifecycle, mil, model, proposals, sil
from .digest import sha256
from .sil import Refused, log_append
from .store import INTEGRITY, Store, canonical
from .verify import verify

NOTICES = "integrity/notices.json"
_LOG = "integrity/log.jsonl"


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
                detail=(
                    "bindings change only outside a session; stop or revoke it first"
                ),
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
            raise Refused(
                "binding-id", "OC-001(a)", "invalid binding id %r" % (target,), [rec]
            )
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
            raise Refused(
                "decommissioned", "OC-002(c)", "already decommissioned", [rec]
            )
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
                detail=(
                    "bindings change only outside a session; stop or revoke it first"
                ),
            )
            raise Refused(
                "session-live",
                "OC-001(a)",
                "bindings change only outside a session; stop or revoke it first",
                [rec],
            )
        try:
            auth = proposals.read_auth(store)
        except (OSError, ValueError) as e:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="authorization-state",
                detail="authorization state unreadable: %s" % (e,),
            )
            raise Refused(
                "authorization-state",
                "OC-001(a)",
                "authorization state unreadable: %s" % (e,),
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
            raise Refused(
                "binding-id", "OC-001(a)", "invalid binding id %r" % (target,), [rec]
            )
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
            raise Refused(
                "decommissioned", "OC-002(c)", "already decommissioned", [rec]
            )
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
        offer = auth.get("ownership_offer")
        if offer and offer.get("to") == target:
            auth.pop("ownership_offer", None)
            proposals.write_auth(store, auth)
        return {"entry": out["entry"], "log_records": [loc["id"], out["log_record"]]}


def ownership_offer(root: str, target: str, *, binding=None):
    """Offer ownership of the Operator binding set to another active binding
    (OC-001(a), D55)."""
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
                detail=(
                    "bindings change only outside a session; stop or revoke it first"
                ),
            )
            raise Refused(
                "session-live",
                "OC-001(a)",
                "bindings change only outside a session; stop or revoke it first",
                [rec],
            )
        try:
            auth = proposals.read_auth(store)
        except (OSError, ValueError) as e:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="authorization-state",
                detail="authorization state unreadable: %s" % (e,),
            )
            raise Refused(
                "authorization-state",
                "OC-001(a)",
                "authorization state unreadable: %s" % (e,),
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
            raise Refused(
                "binding-id", "OC-001(a)", "invalid binding id %r" % (target,), [rec]
            )
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
            raise Refused(
                "owner-only", "OC-001(a)", "only the owner can offer ownership", [rec]
            )
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
                "ownership-self",
                "OC-001(a)",
                "cannot offer ownership to oneself",
                [rec],
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
            raise Refused(
                "decommissioned", "OC-002(c)", "already decommissioned", [rec]
            )
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
                detail=(
                    "bindings change only outside a session; stop or revoke it first"
                ),
            )
            raise Refused(
                "session-live",
                "OC-001(a)",
                "bindings change only outside a session; stop or revoke it first",
                [rec],
            )
        try:
            auth = proposals.read_auth(store)
        except (OSError, ValueError) as e:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="authorization-state",
                detail="authorization state unreadable: %s" % (e,),
            )
            raise Refused(
                "authorization-state",
                "OC-001(a)",
                "authorization state unreadable: %s" % (e,),
                [rec],
            )
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
            raise Refused(
                "decommissioned", "OC-002(c)", "already decommissioned", [rec]
            )
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
            store,
            "ownership-accept",
            binding=acting,
            rule="OC-001(a)",
            offer=offer["record"],
        )
        active = sil.active_bindings(store) or []
        new_content = {"bindings": [{"id": b} for b in active], "owner": acting}
        out = sil.commit_generation(
            store,
            changes={"bindings.json": canonical(new_content)},
            authorization=loc,
        )
        auth.pop("ownership_offer", None)
        proposals.write_auth(store, auth)
        return {
            "entry": out["entry"],
            "owner": acting,
            "log_records": [loc["id"], out["log_record"]],
        }


def ownership_withdraw(root: str, *, binding=None):
    """Withdraw a pending ownership offer (OC-001(a), D55). Owner-only, outside
    session."""
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
                detail=(
                    "bindings change only outside a session; stop or revoke it first"
                ),
            )
            raise Refused(
                "session-live",
                "OC-001(a)",
                "bindings change only outside a session; stop or revoke it first",
                [rec],
            )
        try:
            auth = proposals.read_auth(store)
        except (OSError, ValueError) as e:
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(a)",
                binding=acting,
                check="authorization-state",
                detail="authorization state unreadable: %s" % (e,),
            )
            raise Refused(
                "authorization-state",
                "OC-001(a)",
                "authorization state unreadable: %s" % (e,),
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
                "owner-only",
                "OC-001(a)",
                "only the owner can withdraw an ownership offer",
                [rec],
            )
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
            store,
            "ownership-withdraw",
            binding=acting,
            rule="OC-001(a)",
            offer=offer["record"],
        )
        auth.pop("ownership_offer", None)
        proposals.write_auth(store, auth)
        return {"log_records": [loc["id"]]}


def workspace_crossing(store: Store, path: str):
    """``(ws, limit)`` for the first limit the workspace ``path`` crosses
    (D30), with ``ws`` its real path, or ``None``. Writes nothing."""
    ws = os.path.realpath(os.path.abspath(path))
    limits = [
        os.path.realpath(store.root),
        os.path.realpath(os.path.expanduser("~/.fsp")),
    ]
    for limit in limits:
        if _crosses_boundary(ws, limit):
            return ws, limit
    return None


def set_workspace(root: str, path: str, *, binding=None):
    """Declare the workspace boundary (D28, D30, OC-008(a)(b))."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        crossing = workspace_crossing(store, path)
        if crossing is not None:
            ws, limit = crossing
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
        ws = os.path.realpath(os.path.abspath(path))
        act = sil.operator_act(
            store, "set-workspace", binding=acting, rule="OC-008(a)", workspace=ws
        )
        sil.set_operational(store, "workspace", ws)
        return {"workspace": ws, "log_records": [act]}


def _refuse_model(store, acting, check, detail):
    """Log a refused model change (OC-006) and raise it."""
    rec = log_append(
        store, "refusal", rule="OC-006", binding=acting, check=check, detail=detail
    )
    raise Refused(check, "OC-006", detail, [rec])


def set_model(
    root: str,
    name: str,
    *,
    endpoint=model.DEFAULT_ENDPOINT,
    num_ctx=model.NUM_CTX_DEFAULT,
    binding=None,
):
    """Change the model in use (D87, D28): the model must answer a minimal call
    first, and the change leaves a ``model-fingerprint`` in the log (D36)."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        if not isinstance(name, str) or not name or not model.num_ctx_valid(num_ctx):
            _refuse_model(
                store,
                acting,
                "model-setting",
                "the model needs a name and a num_ctx within %d-%d"
                % model.NUM_CTX_RANGE,
            )
        if not model.local(endpoint):
            _refuse_model(
                store,
                acting,
                "model-endpoint",
                "endpoint %r is not on the local host" % (endpoint,),
            )
    # The call to the model runs outside the lock: it may take long (D87).
    m = model.OllamaModel(
        name, endpoint, num_ctx, config.value(store, "model_timeout_s")
    )
    try:
        m.ping()
    except model.ModelError as e:
        with store.write_lock():
            _refuse_model(
                store, acting, "model", "the model %r did not answer: %s" % (name, e)
            )
    digest = m.digest()
    with store.write_lock():
        # The binding is checked again: it may have changed during the call.
        acting = sil.acting_binding(store, binding)
        act = sil.operator_act(
            store,
            "set-model",
            binding=acting,
            rule="OC-006",
            model=name,
            endpoint=endpoint,
            num_ctx=num_ctx,
        )
        value = {
            "backend": "ollama",
            "name": name,
            "endpoint": endpoint,
            "num_ctx": num_ctx,
            "digest": digest,
        }
        sil.set_operational(store, "model", value)
        fp = log_append(
            store, "model-fingerprint", rule="OC-006", binding=acting, act=act, **value
        )
        live = lifecycle.live_session(root)
        if live is not None:
            mil.save_session(store, live, "model-fingerprint", record=fp)
        return {"model": value, "log_records": [act, fp]}


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
            store,
            "approve",
            binding=acting,
            rule="OC-001(b)",
            proposal=proposal_id,
            digest=digest,
        )
        proposals.record_approval(
            store, proposal_id, digest, loc["id"], acting, authorization=loc
        )
        return {"log_records": [loc["id"]]}


def grant(root: str, *, expiry=None, budget=None, scope=None, binding=None):
    """Open an authorization window (D17, D59, OC-001(b))."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)

        for axis_name, axis_val in (
            ("expiry", expiry),
            ("budget", budget),
            ("scope", scope),
        ):
            if axis_val is None or axis_val == "":
                detail = "a window is bounded on all three axes: --%s is missing" % (
                    axis_name,
                )
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


def review_list(root: str, *, binding=None):
    """Pending evolution proposals, approved or not, in order of origination
    (D52). Read-only."""
    store = Store(root)
    with store.write_lock():
        try:
            auth = proposals.read_auth(store)
        except (OSError, ValueError) as e:
            raise Refused(
                "authorization-state",
                "OC-001(b)",
                "authorization state unreadable: %s" % (e,),
            )
        items = []
        for pid, entry in auth["proposals"].items():
            items.append(
                {
                    "proposal": pid,
                    "digest": entry["digest"],
                    "session": entry["session"],
                    "record": entry["record"],
                    "categories": sorted(
                        set(proposals.CATEGORIES[op["op"]] for op in entry["ops"])
                    ),
                    "approved": pid in auth["approvals"],
                }
            )
        items.sort(key=lambda it: it["record"])
        promotions = [
            {
                "promotion": r["id"],
                "slug": r["slug"],
                "category": r["category"],
                "content": r["content"],
                "supersedes": r["supersedes"],
                "digest": r["digest"],
                "session": r["session"],
                "conversation": r["conversation"],
            }
            for r in mil.pending_promotions(store)
            if r.get("id") not in auth["promotions"]
        ]
        return {"proposals": items, "promotions": promotions}


def _undecided_promotion(store: Store, acting, promotion_id):
    """The authorization state and the request ``promotion_id`` names, when the
    Operator has not decided it yet (OC-001(b), D53). An unknown or decided
    promotion is refused and logged."""
    try:
        auth = proposals.read_auth(store)
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
    request = next(
        (r for r in mil.pending_promotions(store) if r.get("id") == promotion_id),
        None,
    )
    if request is None:
        check, detail = "promotion-unknown", "promotion %r is not known"
    elif promotion_id in auth["promotions"]:
        check, detail = "promotion-decided", "promotion %r is already decided"
    else:
        return auth, request
    detail = detail % (promotion_id,)
    rec = log_append(
        store,
        "refusal",
        rule="OC-001(b)",
        binding=acting,
        check=check,
        detail=detail,
    )
    raise Refused(check, "OC-001(b)", detail, [rec])


def approve_promotion(root: str, promotion_id: str, *, edit=None, binding=None):
    """Approve a promotion request as it stands or with the Operator's own text
    (OC-001(b), D53, D80). The approval names the digest of the text approved;
    an edit passes the same checks and probes as the request (OC-002(d))."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        auth, request = _undecided_promotion(store, acting, promotion_id)
        if edit is None:
            digest = request["digest"]
        else:
            if not isinstance(edit, dict) or set(edit) != {
                "slug",
                "category",
                "content",
            }:
                detail = "an edit is an object with exactly slug, category and content"
                rec = log_append(
                    store,
                    "refusal",
                    rule="OC-001(b)",
                    binding=acting,
                    check="promotion-edit",
                    detail=detail,
                )
                raise Refused("promotion-edit", "OC-001(b)", detail, [rec])
            mil._check_promotion(
                store,
                None,
                edit["slug"],
                edit["category"],
                edit["content"],
                binding=acting,
            )
            digest = mil.promotion_digest(
                edit["slug"], edit["category"], edit["content"], request["supersedes"]
            )
        loc = sil.operator_act_located(
            store,
            "approve-promotion",
            binding=acting,
            rule="OC-001(b)",
            promotion=promotion_id,
            digest=digest,
        )
        auth["promotions"][promotion_id] = {
            "digest": digest,
            "record": loc["id"],
            "binding": acting,
            "authorization": loc,
            "edit": edit,
        }
        proposals.write_auth(store, auth)
        return {
            "promotion": promotion_id,
            "digest": digest,
            "log_records": [loc["id"]],
        }


def reject_promotion(root: str, promotion_id: str, *, binding=None):
    """Reject a promotion request (OC-001(b), D53, D80)."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        auth, _request = _undecided_promotion(store, acting, promotion_id)
        act = sil.operator_act(
            store,
            "reject-promotion",
            binding=acting,
            rule="OC-001(b)",
            promotion=promotion_id,
        )
        auth["promotions"][promotion_id] = {"rejected": act, "binding": acting}
        proposals.write_auth(store, auth)
        return {"promotion": promotion_id, "log_records": [act]}


def retract_semantic(root: str, record_id: str, *, binding=None):
    """Retract a semantic record: an Operator act appended to the semantic
    ledger, after which the record leaves recall (OP-009(f), D53, D81)."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        ledger = sil.semantic_ledger(store)
        if not any(
            e.get("kind") == "promotion" and e.get("id") == record_id for e in ledger
        ):
            check, detail = "semantic-unknown", "semantic record %r is not known"
        elif any(
            e.get("kind") == "retraction" and e.get("id") == record_id for e in ledger
        ):
            check, detail = "semantic-retracted", "semantic record %r is retracted"
        else:
            act = sil.operator_act(
                store,
                "retract-semantic",
                binding=acting,
                rule="OP-009(f)",
                record=record_id,
            )
            sil.semantic_ledger_append(
                store, {"kind": "retraction", "id": record_id, "act": act}
            )
            return {"record": record_id, "log_records": [act]}
        detail = detail % (record_id,)
        rec = log_append(
            store,
            "refusal",
            rule="OP-009(f)",
            binding=acting,
            check=check,
            detail=detail,
        )
        raise Refused(check, "OP-009(f)", detail, [rec])


def reject(root: str, proposal_id: str, *, binding=None):
    """Reject a pending evolution proposal and withdraw its approval, if any
    (OC-001(b), D52)."""
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
        act = sil.operator_act(
            store,
            "reject",
            binding=acting,
            rule="OC-001(b)",
            proposal=proposal_id,
            digest=prop["digest"],
        )
        auth["proposals"].pop(proposal_id, None)
        auth["approvals"].pop(proposal_id, None)
        proposals.write_auth(store, auth)
        return {"log_records": [act]}


def _notice_start(store: Store):
    """Where the notice listing starts reading the log, and whether the stored
    pointer was discarded (D66). A pointer that does not match the log, or that
    is malformed or unreadable, restarts the listing at the beginning."""
    if not store.exists(NOTICES):
        return 0, False
    try:
        ptr = store.read_json(NOTICES)
    except (OSError, ValueError):
        return 0, True
    if not (
        isinstance(ptr, dict)
        and set(ptr) == {"id", "offset", "sha256"}
        and isinstance(ptr["offset"], int)
        and not isinstance(ptr["offset"], bool)
        and ptr["offset"] >= 0
        and isinstance(ptr["id"], str)
        and isinstance(ptr["sha256"], str)
    ):
        return 0, True
    line = store.read_line_at(_LOG, ptr["offset"])
    if line is None or sha256(line) != ptr["sha256"]:
        return 0, True
    try:
        rec = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return 0, True
    if not (isinstance(rec, dict) and rec.get("id") == ptr["id"]):
        return 0, True
    return ptr["offset"] + len(line) + 1, False


def _pending(store: Store):
    """The operator notices logged after the last acknowledgement, as
    ``(rec, offset, line)`` tuples, and whether the pointer was discarded (D66).
    A log line that does not decode is skipped, so damage elsewhere in the log
    hides no notice."""
    start, reset = _notice_start(store)
    data = store.read_from(_LOG, start)
    pending = []
    cur = start
    for line in data.split(b"\n")[:-1]:
        try:
            rec = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            rec = None
        if isinstance(rec, dict) and rec.get("kind") == "operator-notification":
            pending.append((rec, cur, line))
        cur += len(line) + 1
    return pending, reset


def notifications(root: str, *, binding=None):
    """The operator notices pending, logged after the Operator's last
    acknowledgement (D66). Read-only."""
    store = Store(root)
    with store.write_lock():
        pending, reset = _pending(store)
        return {"notifications": [rec for rec, _, _ in pending], "pointer_reset": reset}


def clear_transcript(root: str, *, binding=None):
    """Cut the transcript of the live session's conversation, as a recorded
    Operator act (D13, D78). It neither counts as an entity operation nor
    triggers a Vital Check."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        session = lifecycle.require_session(root, "clear-transcript")
        act = sil.operator_act(
            store,
            "clear-transcript",
            binding=acting,
            rule="OP-009(a)",
            session=session,
        )
        rid = mil.save_session(store, session, "transcript-cleared", act=act)
        return {"record": rid, "log_records": [act]}


def exit_conversation(root: str, payload, *, binding=None):
    """End the live session's conversation with a Closure Payload (D84,
    OP-009(a)(d)(e)). The payload is checked before anything is written; a
    refusal leaves the session live. Otherwise the act and the payload are
    recorded, then the session closes and its Sleep consolidates."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        session = lifecycle.require_session(root, "exit")
        mil.check_closure_payload(store, session, payload)
        act = sil.operator_act(
            store, "exit", binding=acting, rule="OP-009(a)", session=session
        )
        rid = mil.save_session(
            store, session, "closure-payload", payload=payload, act=act
        )
        out = lifecycle.close_session(store, session, acting)
        return {**out, "closure": rid, "log_records": [act] + out["log_records"]}


def exit_with_closure(root: str, *, channel=None, binding=None, date=None):
    """End the live session's conversation with a Closure Payload that
    cognition emits in a call of its own (D91, OP-009(d)). A refused emission
    or a refused payload (D84) propagates, and the session stays live."""
    emitted = cycle.emit_closure(root, channel=channel, date=date)
    out = exit_conversation(root, emitted["payload"], binding=binding)
    return {**out, "cycle": emitted["cycle"]}


def new_conversation(root: str, *, binding=None):
    """Leave the live session's conversation with no payload and close the
    session (D84, OP-009(a))."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        session = lifecycle.require_session(root, "new")
        act = sil.operator_act(
            store, "new", binding=acting, rule="OP-009(a)", session=session
        )
        mil.save_session(store, session, "conversation-left", act=act)
        out = lifecycle.close_session(store, session, acting)
        return {**out, "log_records": [act] + out["log_records"]}


def _refuse_conversation_act(store: Store, acting, check, detail):
    """Log the refusal of /inject or /resume and raise it (D85, OP-009(g))."""
    rec = log_append(
        store,
        "refusal",
        rule="OP-009(g)",
        binding=acting,
        check=check,
        detail=detail,
    )
    raise Refused(check, "OP-009(g)", detail, [rec])


def inject_records(root: str, conversation, records=None, *, binding=None):
    """Add the episodic records of a past conversation, all or those named, to
    the live conversation's pointer map, as an Operator act (D85,
    OP-009(g))."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        session = lifecycle.require_session(root, "inject")
        current = mil.conversation_of(store, session)
        if conversation == current:
            _refuse_conversation_act(
                store,
                acting,
                "conversation-current",
                "conversation %r is the current one" % (conversation,),
            )
        own = [
            r["id"]
            for r in mil._episodic(store)
            if r.get("conversation") == conversation and isinstance(r.get("id"), str)
        ]
        if not own:
            _refuse_conversation_act(
                store,
                acting,
                "conversation-unknown",
                "conversation %r has no episodic record" % (conversation,),
            )
        if records is None:
            ids = own
        elif isinstance(records, list) and all(
            isinstance(i, str) and i in own for i in records
        ):
            ids = records
        else:
            _refuse_conversation_act(
                store,
                acting,
                "recall-scope",
                "a named record was not written by conversation %r" % (conversation,),
            )
        act = sil.operator_act(
            store,
            "inject",
            binding=acting,
            rule="OP-009(g)",
            session=session,
            conversation=conversation,
            records=ids,
        )
        added = mil.add_pointers(
            store, current, ids, source=conversation, via="inject", act=act
        )
        return {"added": added, "log_records": [act]}


def resume_conversation(root: str, conversation, *, binding=None):
    """Leave the live conversation and close the session so that the next
    start continues a past conversation's last session, as an Operator act
    (D85, OP-009(g))."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        session = lifecycle.require_session(root, "resume")
        current = mil.conversation_of(store, session)
        if conversation == current:
            _refuse_conversation_act(
                store,
                acting,
                "conversation-current",
                "conversation %r is the current one" % (conversation,),
            )
        last = mil.last_session_of(store, conversation, int(session[2:]))
        if last is None:
            _refuse_conversation_act(
                store,
                acting,
                "conversation-unknown",
                "conversation %r was never opened" % (conversation,),
            )
        act = sil.operator_act(
            store,
            "resume",
            binding=acting,
            rule="OP-009(g)",
            session=session,
            conversation=conversation,
        )
        mil.save_session(
            store,
            session,
            "conversation-left",
            act=act,
            resume={"conversation": conversation, "session": last},
        )
        out = lifecycle.close_session(store, session, acting)
        return {**out, "log_records": [act] + out["log_records"]}


def acknowledge_notifications(root: str, *, binding=None):
    """Acknowledge every pending operator notice, as a recorded Operator act
    (D66). Writes nothing when no notice is pending."""
    store = Store(root)
    with store.write_lock():
        acting = sil.acting_binding(store, binding)
        pending, _ = _pending(store)
        if not pending:
            return {"acknowledged": [], "log_records": []}
        rec, offset, line = pending[-1]
        act = sil.operator_act(
            store,
            "notifications-acknowledged",
            binding=acting,
            rule="OP-008(a)",
            through=rec["id"],
            count=len(pending),
        )
        store.replace_json(
            INTEGRITY,
            NOTICES,
            {"id": rec["id"], "offset": offset, "sha256": sha256(line)},
            writer=sil.WRITER,
        )
        return {"acknowledged": [r["id"] for r, _, _ in pending], "log_records": [act]}
