# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Proposals, approvals and proposal commit (D57, D58)."""

from __future__ import annotations

from datetime import datetime, timedelta
import posixpath
import re
import secrets

from . import chain, clock, config, lifecycle, sil, vital
from . import manifest as skill_manifest
from .digest import canonical, integrity_document, sha256
from .sil import WRITER, Refused, log_append
from .store import DOMAIN_ENTRY, INTEGRITY, SKILL_NAME, Store

CATEGORIES = {
    "set-persona": "persona",
    "install-skill": "skills.install",
    "allow-skill": "rules",
    "deny-skill": "rules",
    "unset-skill": "rules",
    "allow-domain": "rules",
    "deny-domain": "rules",
    "unset-domain": "rules",
    "set-parameter": "parameters",
}

DOMAIN_OPS = ("allow-domain", "deny-domain", "unset-domain")
RULE_OPS = ("allow-skill", "deny-skill", "unset-skill") + DOMAIN_OPS

WINDOW_CATEGORIES = (
    "skills.install",
    "skills.update",
    "skills.remove",
    "rules",
    "parameters",
    "memory.semantic",
)

EXPIRY_RE = re.compile(r"^([+-])(\d+)([smhd])\Z")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}\Z")


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
        return {"proposals": {}, "approvals": {}, "promotions": {}, "grants": []}
    data = store.read_json(lifecycle.AUTH)
    if not isinstance(data, dict):
        raise ValueError("authorization state is not an object")
    proposals_obj = data.get("proposals")
    if proposals_obj is not None and not isinstance(proposals_obj, dict):
        raise ValueError("proposals must be an object")
    approvals_obj = data.get("approvals")
    if approvals_obj is not None and not isinstance(approvals_obj, dict):
        raise ValueError("approvals must be an object")
    promotions_obj = data.get("promotions")
    if promotions_obj is not None and not isinstance(promotions_obj, dict):
        raise ValueError("promotions must be an object")
    grants_obj = data.get("grants")
    if grants_obj is not None and not isinstance(grants_obj, list):
        raise ValueError("grants must be a list")
    if "ownership_offer" in data and data["ownership_offer"] is not None:
        offer = data["ownership_offer"]
        if (
            not isinstance(offer, dict)
            or set(offer.keys()) != {"to", "record", "binding"}
            or not all(isinstance(v, str) for v in offer.values())
        ):
            raise ValueError("ownership offer is malformed")
    if "proposals" not in data:
        data["proposals"] = {}
    if "approvals" not in data:
        data["approvals"] = {}
    if "promotions" not in data:
        data["promotions"] = {}
    if "grants" not in data:
        data["grants"] = []
    return data


def write_auth(store: Store, auth: dict) -> None:
    """Write authorization state (lifecycle.AUTH)."""
    store.replace_json(INTEGRITY, lifecycle.AUTH, auth, writer=WRITER)


def promotion_authorization(store: Store, root, promotion_id, request, *, session):
    """Validate and consume the authorization of a promotion (D53, D81).

    Returns ``(text, authorization, window)`` or ``None`` when the request has
    none. An approval names the digest of the text: the Operator's edit, or the
    request's, recomputed; a text that no longer matches is not promoted. With
    no approval, the first open window over ``memory.semantic`` covers it, and
    its budget is spent as a commit spends it. Called with the store lock
    held."""
    from . import mil  # imported here to avoid an import cycle

    auth = read_auth(store)
    entry = auth["promotions"].get(promotion_id)
    if isinstance(entry, dict) and "rejected" in entry:
        return None
    request_text = {k: request[k] for k in ("slug", "category", "content")}
    if isinstance(entry, dict) and "digest" in entry:
        text = entry["edit"] if entry.get("edit") else request_text
        digest = mil.promotion_digest(
            text["slug"], text["category"], text["content"], request["supersedes"]
        )
        if digest != entry["digest"]:
            return None
        return text, entry["authorization"], None

    if close_lapsed(store, clock.grant_now(root), session=session):
        auth = read_auth(store)
    for g in auth.get("grants", []):
        if g.get("state") == "open" and covers(g.get("scope", ""), "memory.semantic"):
            g["used"] = g.get("used", 0) + 1
            if g["used"] >= g["budget"]:
                g["state"] = "closed"
                g["closed"] = "exhausted"
                log_append(
                    store,
                    "grant-closed",
                    rule="OC-001(b)",
                    session=session,
                    grant=g["id"],
                    reason="exhausted",
                )
            write_auth(store, auth)
            return request_text, g.get("authorization"), g["id"]
    return None


def open_window(
    store: Store,
    *,
    scope: str,
    expires: datetime,
    budget: int,
    record: str,
    binding: str,
    authorization: dict,
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
        "authorization": authorization,
    }
    auth["grants"].append(window)
    write_auth(store, auth)


def close_lapsed(store: Store, now: datetime, *, session: str = None) -> list[str]:
    """Close open windows that have expired or exhausted their budget
    (OC-001(b), D59)."""
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


def _refuse_ops(store: Store, rule, check, detail, *, session, binding):
    rec = log_append(
        store,
        "refusal",
        rule=rule,
        session=session,
        binding=binding,
        check=check,
        detail=detail,
    )
    raise Refused(check, rule, detail, [rec])


def _validate_ops(store: Store, ops, *, session=None, binding=None) -> list:
    """Validate ``ops`` as a proposal's ops and return them normalized,
    logging and raising the refusal of the first that fails, with the store's
    write lock held (D57, D96)."""
    from . import mil  # imported here to avoid an import cycle

    def refuse(rule, check, detail):
        _refuse_ops(store, rule, check, detail, session=session, binding=binding)

    # 1. ops is a non-empty list of dicts each with an "op" string
    if not (
        isinstance(ops, list)
        and len(ops) > 0
        and all(isinstance(op, dict) and isinstance(op.get("op"), str) for op in ops)
    ):
        refuse("OC-001(b)", "ops", "invalid ops format")

    # 2. binding set cannot be targeted
    if any(op.get("op") in ("add-binding", "remove-binding") for op in ops):
        refuse(
            "OC-001(a)",
            "binding-set",
            "a proposal cannot change the Operator binding set",
        )

    # 3. validate each op
    for op in ops:
        op_name = op["op"]
        if op_name not in CATEGORIES:
            refuse("OC-001(b)", "op-unknown", "unknown operation %r" % (op_name,))
        if op_name == "set-persona":
            content = op.get("content")
            if not isinstance(content, str):
                refuse("OC-001(b)", "ops", "set-persona requires a string content")
        elif op_name == "install-skill":
            name = op.get("name")
            if not (isinstance(name, str) and SKILL_NAME.match(name)):
                refuse("OC-001(b)", "ops", "install-skill has invalid skill name")
            files = op.get("files")
            if not (
                isinstance(files, dict)
                and len(files) > 0
                and all(
                    isinstance(k, str) and isinstance(v, str) for k, v in files.items()
                )
            ):
                refuse(
                    "OC-001(b)",
                    "ops",
                    "install-skill requires a non-empty files dict of strings",
                )
            for file_path in files:
                if not _is_valid_skill_path(file_path):
                    refuse(
                        "OC-001(b)",
                        "ops",
                        "invalid skill file path %r" % (file_path,),
                    )
        elif op_name in DOMAIN_OPS:
            domain = op.get("domain")
            if not (isinstance(domain, str) and DOMAIN_ENTRY.match(domain)):
                refuse("OC-001(b)", "ops", "%s has invalid domain" % (op_name,))
        elif op_name in RULE_OPS:
            name = op.get("name")
            if not (isinstance(name, str) and SKILL_NAME.match(name)):
                refuse("OC-001(b)", "ops", "%s has invalid skill name" % (op_name,))
            if op_name == "allow-skill":
                digest = op.get("digest")
                if not (isinstance(digest, str) and DIGEST_RE.match(digest)):
                    refuse("OC-001(b)", "ops", "allow-skill requires a sha256 digest")
        elif op_name == "set-parameter":
            value = op.get("value")
            if not (
                op.get("name") == "always_loaded"
                and isinstance(value, list)
                and len(value) > 0
                and all(isinstance(c, str) and c in mil.CATEGORIES for c in value)
                and len(set(value)) == len(value)
            ):
                refuse(
                    "OC-001(b)",
                    "ops",
                    "set-parameter requires the name always_loaded and a non-empty "
                    "list of distinct categories",
                )

    # 4. no duplicate write targets
    targets = set()
    rule_targets = set()
    for op in ops:
        op_name = op["op"]
        if op_name == "set-persona":
            target = "persona.md"
            if target in targets:
                refuse("OC-001(b)", "ops", "duplicate write target %r" % (target,))
            targets.add(target)
        elif op_name == "install-skill":
            name = op["name"]
            for file_path in op["files"]:
                target = "skills/%s/%s" % (name, file_path)
                if target in targets:
                    refuse("OC-001(b)", "ops", "duplicate write target %r" % (target,))
                targets.add(target)
        elif op_name in DOMAIN_OPS:
            domain = op["domain"]
            if ("domain", domain) in rule_targets:
                refuse(
                    "OC-001(b)",
                    "rule-target",
                    "domain %r is named by more than one op" % (domain,),
                )
            rule_targets.add(("domain", domain))
        elif op_name in RULE_OPS:
            name = op["name"]
            if ("skill", name) in rule_targets:
                refuse(
                    "OC-001(b)",
                    "rule-target",
                    "skill %r is named by more than one op" % (name,),
                )
            rule_targets.add(("skill", name))

    # 7. normalize ops
    normalized = []
    for op in ops:
        op_name = op["op"]
        if op_name == "set-persona":
            normalized.append({"op": "set-persona", "content": op["content"]})
        elif op_name == "install-skill":
            normalized.append(
                {
                    "op": "install-skill",
                    "name": op["name"],
                    "files": dict(op["files"]),
                }
            )
        elif op_name == "allow-skill":
            normalized.append(
                {
                    "op": "allow-skill",
                    "name": op["name"],
                    "digest": op["digest"],
                }
            )
        elif op_name in ("deny-skill", "unset-skill"):
            normalized.append({"op": op_name, "name": op["name"]})
        elif op_name in DOMAIN_OPS:
            normalized.append({"op": op_name, "domain": op["domain"]})
        elif op_name == "set-parameter":
            normalized.append(
                {
                    "op": "set-parameter",
                    "name": op["name"],
                    "value": list(op["value"]),
                }
            )
    return normalized


def propose(root: str, ops: list) -> dict:
    """Originate an evolution proposal from ops (D57, D58, OC-001(b))."""
    store = Store(root)
    with store.write_lock():
        # 1-4, 7. validate and normalize the ops
        normalized = _validate_ops(store, ops)

        # 5. require live session
        session = vital.require_entity_session(root, "propose")

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

        # 6b. pending cap (D52, D96)
        cap = config.value(store, "pending_cap")
        own = sum(
            1 for p in auth["proposals"].values() if p.get("origin") != "operator"
        )
        if own >= cap:
            detail = "%d proposals pending; the cap is %d" % (own, cap)
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(b)",
                session=session,
                check="pending-cap",
                detail=detail,
            )
            raise Refused("pending-cap", "OC-001(b)", detail, [rec])

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
        if sil.current_cycle() is not None:
            auth["proposals"][pid]["cycle"] = sil.current_cycle()
        write_auth(store, auth)

        # 10. return
        return {"proposal": pid, "log_records": [rec]}


def record_operator_proposal(store: Store, ops: list, *, binding: str) -> dict:
    """Record the Operator's own structural act: a proposal and its approval,
    with the write lock held (D96, OP-011(a)). Needs no session, counts
    against no cap and commits nothing."""
    normalized = _validate_ops(store, ops, binding=binding)
    auth = read_auth(store)
    digest = sha256(canonical(normalized))
    pid = "P-" + secrets.token_hex(8)
    categories = sorted(list(set(CATEGORIES[op["op"]] for op in normalized)))
    rec = log_append(
        store,
        "proposal",
        rule="OC-001(b)",
        binding=binding,
        proposal=pid,
        digest=digest,
        categories=categories,
        ops=normalized,
        origin="operator",
    )
    auth["proposals"][pid] = {
        "digest": digest,
        "ops": normalized,
        "record": rec,
        "session": None,
        "origin": "operator",
        "binding": binding,
    }
    if sil.current_cycle() is not None:
        auth["proposals"][pid]["cycle"] = sil.current_cycle()
    write_auth(store, auth)
    loc = sil.operator_act_located(
        store,
        "approve",
        binding=binding,
        rule="OC-001(b)",
        proposal=pid,
        digest=digest,
    )
    record_approval(store, pid, digest, loc["id"], binding, authorization=loc)
    return {"proposal": pid, "digest": digest, "log_records": [rec, loc["id"]]}


def attempt_propose(store: Store, cls, target):
    """propose's attempted write: the SIL records a proposal, so propose
    writes no content class and refuses every one (D68)."""
    raise sil.refuse_attempt(
        store,
        "sole-writer",
        "propose writes no content class; the SIL records a proposal",
        via="propose",
        content_class=cls,
        target=target,
    )


def record_approval(
    store: Store,
    pid: str,
    digest: str,
    record: str,
    binding: str,
    *,
    authorization: dict,
) -> None:
    """Record an Operator approval for a proposal."""
    auth = read_auth(store)
    entry = {
        "digest": digest,
        "record": record,
        "binding": binding,
        "authorization": authorization,
    }
    auth["approvals"][pid] = entry
    write_auth(store, auth)


def _skill_files(document, changes, name):
    """The ``{path, sha256, exec}`` entries of the skill ``name`` in the
    generation a commit builds from ``document`` and ``changes``, as
    ``sil.commit_generation`` writes it (D70, D16)."""
    prefix = "skills/%s/" % (name,)
    entries = {e["path"]: e for e in document if e["path"].startswith(prefix)}
    for path, data in changes.items():
        if not path.startswith(prefix):
            continue
        if data is None:
            entries.pop(path, None)
        else:
            existing = entries.get(path)
            entries[path] = {
                "path": path,
                "sha256": sha256(data),
                "exec": existing["exec"] if existing is not None else False,
            }
    return sorted(entries.values(), key=lambda f: f["path"])


def head_skill_digest(store: Store, name: str):
    """The digest of skill ``name`` in the head generation, computed as a
    commit computes it (D16, D70), or ``None`` when the head holds no file of
    that skill."""
    gen = chain.gen_relpath(sil.read_head(store)["entry"])
    document = integrity_document(store.path(gen))[0]
    files = _skill_files(document, {}, name)
    if not files:
        return None
    return skill_manifest.skill_digest(files)


def _refuse_rule(store: Store, session, detail: str):
    rec = log_append(
        store,
        "refusal",
        rule="OC-001(b)",
        session=session,
        check="rule-target",
        detail=detail,
    )
    raise Refused("rule-target", "OC-001(b)", detail, [rec])


def _rules_change(store, head, changes, ops, session):
    """Apply the proposal's rule ops to the ``rules.json`` of the generation
    being committed and return its new bytes (D70)."""
    gen = chain.gen_relpath(head["entry"])
    try:
        rules = store.read_json(gen + "/rules.json")
    except (OSError, ValueError):
        rules = None
    if not (
        isinstance(rules, dict)
        and isinstance(rules.get("skills"), dict)
        and isinstance(rules.get("domains"), dict)
    ):
        _refuse_rule(
            store,
            session,
            "the rules of generation %d cannot be read as rules" % (head["entry"],),
        )
    skills = rules["skills"]
    domains = rules["domains"]
    document = integrity_document(store.path(gen))[0]
    for op in ops:
        if op["op"] in DOMAIN_OPS:
            domain = op["domain"]
            if op["op"] == "allow-domain":
                domains[domain] = {"rule": "allow"}
            elif op["op"] == "deny-domain":
                domains[domain] = {"rule": "deny"}
            else:
                if domain not in domains:
                    _refuse_rule(
                        store,
                        session,
                        "the rules hold no entry for domain %r" % (domain,),
                    )
                del domains[domain]
            continue
        name = op["name"]
        if op["op"] == "allow-skill":
            files = _skill_files(document, changes, name)
            if not files:
                _refuse_rule(
                    store,
                    session,
                    "skill %r is not in the generation being committed" % (name,),
                )
            actual = skill_manifest.skill_digest(files)
            if actual != op["digest"]:
                _refuse_rule(
                    store,
                    session,
                    "the digest of skill %r is %s, not %s"
                    % (name, actual, op["digest"]),
                )
            skills[name] = {"rule": "allow", "digest": op["digest"]}
        elif op["op"] == "deny-skill":
            skills[name] = {"rule": "deny"}
        else:
            if name not in skills:
                _refuse_rule(
                    store,
                    session,
                    "the rules hold no entry for skill %r" % (name,),
                )
            del skills[name]
    return canonical(rules)


def _config_change(store, head, ops, session):
    """Apply the proposal's ``set-parameter`` ops, in order, to the
    ``config.json`` of the generation being committed and return its new
    bytes (D96)."""
    gen = chain.gen_relpath(head["entry"])
    try:
        settings = store.read_json(gen + "/config.json")
    except (OSError, ValueError):
        settings = None
    if not isinstance(settings, dict):
        rec = log_append(
            store,
            "refusal",
            rule="OC-001(b)",
            session=session,
            check="parameter-target",
            detail="the config of generation %d cannot be read as settings"
            % (head["entry"],),
        )
        raise Refused(
            "parameter-target",
            "OC-001(b)",
            "the config of generation %d cannot be read as settings" % (head["entry"],),
            [rec],
        )
    for op in ops:
        settings[op["name"]] = list(op["value"])
    return canonical(settings)


def _window_open(grant, now_iso: str) -> bool:
    """Whether ``grant`` is open and neither expired nor exhausted at
    ``now_iso``, without closing it (D59)."""
    if grant.get("state") != "open":
        return False
    if grant.get("expires") and grant["expires"] <= now_iso:
        return False
    return grant.get("used", 0) < grant.get("budget", 0)


def _authorization(store: Store, auth: dict, prop: dict, now: datetime, *, proposal_id):
    """The authorization that covers ``prop`` now: ``(record, authorization,
    grant)`` — ``grant`` the covering window, or ``None`` for an approval — or
    ``None`` when nothing covers it. An approval naming the proposal's digest
    comes first, then the first open window over every category the proposal
    touches (D50, D58, D59). Writes and logs nothing."""
    appr = auth.get("approvals", {}).get(proposal_id)
    if appr is not None and appr.get("digest") == prop["digest"]:
        return appr["record"], appr.get("authorization"), None
    categories = set(CATEGORIES.get(op.get("op")) for op in prop["ops"])
    if "persona" in categories or None in categories:
        return None
    now_iso = clock.iso(now)
    for g in auth.get("grants", []):
        if _window_open(g, now_iso) and all(
            covers(g.get("scope", ""), cat) for cat in categories
        ):
            return g["id"], g.get("authorization"), g
    return None


def _refusal_detail(auth: dict, prop: dict, closed_now: list) -> str:
    """Why nothing authorizes ``prop``, as ``commit`` refuses it (D58)."""
    categories = set(CATEGORIES.get(op.get("op")) for op in prop["ops"])
    reasons = ["no per-proposal approval"]
    if closed_now:
        reasons.append("windows closed: %s" % ", ".join(closed_now))
    if "persona" in categories:
        reasons.append("persona cannot be authorized by a window")
    elif any(g.get("state") == "open" for g in auth.get("grants", [])):
        reasons.append("no open window covers categories %s" % sorted(list(categories)))
    else:
        reasons.append("no open window")
    return "; ".join(reasons)


def commit(root: str, proposal_id: str) -> dict:
    """Commit an authorized proposal (D57, D58, OC-001(b))."""
    session = vital.require_entity_session(root, "commit")
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
        now = clock.grant_now(root)
        closed_now = []
        appr = auth.get("approvals", {}).get(proposal_id)
        if not (appr is not None and appr.get("digest") == prop["digest"]):
            closed_now = close_lapsed(store, now, session=session)
            if closed_now:
                auth = read_auth(store)
                prop = auth["proposals"][proposal_id]
        if _authorization(store, auth, prop, now, proposal_id=proposal_id) is None:
            detail = _refusal_detail(auth, prop, closed_now)
            rec = log_append(
                store,
                "refusal",
                rule="OC-001(b)",
                session=session,
                check="authorization",
                detail=detail,
            )
            raise Refused("authorization", "OC-001(b)", detail, [rec])

        return _commit(store, proposal_id, session=session)


def _commit(store: Store, proposal_id: str, *, session) -> dict:
    """The commit of an authorized proposal, with the write lock held (D58,
    D94): ``commit`` and the Endure phase both call it. The proposal is marked
    in ``auth.json`` before ``HEAD`` can move (D94)."""
    auth = read_auth(store)
    prop = auth.get("proposals", {}).get(proposal_id)
    authorized = None
    if prop is not None:
        authorized = _authorization(
            store, auth, prop, clock.grant_now(store.root), proposal_id=proposal_id
        )
    if authorized is None:
        detail = "proposal %r has no authorization" % (proposal_id,)
        rec = log_append(
            store,
            "refusal",
            rule="OC-001(b)",
            session=session,
            check="authorization",
            detail=detail,
        )
        raise Refused("authorization", "OC-001(b)", detail, [rec])
    auth_record, auth_loc, covering_grant = authorized

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

    rule_ops = [op for op in prop["ops"] if op["op"] in RULE_OPS]
    if rule_ops:
        changes["rules.json"] = _rules_change(store, head, changes, rule_ops, session)
    parameter_ops = [op for op in prop["ops"] if op["op"] == "set-parameter"]
    if parameter_ops:
        changes["config.json"] = _config_change(store, head, parameter_ops, session)

    prop["committing"] = {
        "entry": head["entry"] + 1,
        "grant": covering_grant["id"] if covering_grant is not None else None,
    }
    write_auth(store, auth)
    try:
        out = sil.commit_generation(
            store, changes=changes, authorization=auth_loc, session=session
        )
    except Refused:
        del prop["committing"]
        write_auth(store, auth)
        raise

    log_records = [out["log_record"]]
    if covering_grant is not None:
        rec_closed = _spend(store, covering_grant, session)
        if rec_closed is not None:
            log_records.append(rec_closed)

    auth["proposals"].pop(proposal_id, None)
    auth["approvals"].pop(proposal_id, None)
    write_auth(store, auth)

    return {
        "authorization": auth_record,
        "entry": out["entry"],
        "log_records": log_records,
    }


def _spend(store: Store, grant: dict, session):
    """Spend one use of ``grant``'s budget and close it when exhausted
    (D59). Returns the id of the ``grant-closed`` record, or ``None``."""
    grant["used"] = grant.get("used", 0) + 1
    if grant["used"] < grant["budget"]:
        return None
    grant["state"] = "closed"
    grant["closed"] = "exhausted"
    return log_append(
        store,
        "grant-closed",
        rule="OC-001(b)",
        session=session,
        grant=grant["id"],
        reason="exhausted",
    )


def resolve_interrupted(store: Store) -> list:
    """Finish or undo the commits a crash interrupted, with the write lock
    held, and return the ids of the records logged (D94). A proposal marked
    ``committing`` whose entry ``HEAD`` has reached was committed: its
    bookkeeping is finished as ``commit`` finishes it. Otherwise the mark is
    cleared and the proposal waits."""
    auth = read_auth(store)
    marked = [
        pid
        for pid, prop in auth["proposals"].items()
        if isinstance(prop, dict) and "committing" in prop
    ]
    if not marked:
        return []
    head_entry = sil.read_head(store)["entry"]
    records = []
    for pid in marked:
        mark = auth["proposals"][pid]["committing"]
        if not (
            isinstance(mark, dict)
            and type(mark.get("entry")) is int
            and (mark.get("grant") is None or isinstance(mark["grant"], str))
        ):
            raise ValueError("commit mark of proposal %r is malformed" % (pid,))
        if head_entry < mark["entry"]:
            del auth["proposals"][pid]["committing"]
            continue
        grant = None
        if mark["grant"] is not None:
            grant = next(
                (g for g in auth["grants"] if g.get("id") == mark["grant"]), None
            )
        if grant is not None:
            closed = _spend(store, grant, None)
            if closed is not None:
                records.append(closed)
        auth["proposals"].pop(pid)
        auth["approvals"].pop(pid, None)
        records.append(
            log_append(
                store,
                "commit-recovered",
                rule="OC-004(b)",
                proposal=pid,
                entry=mark["entry"],
            )
        )
    write_auth(store, auth)
    return records


def _by_origination(auth: dict) -> list:
    """The ids of the pending proposals, in order of their origination
    records."""
    return sorted(
        auth["proposals"],
        key=lambda pid: (
            len(auth["proposals"][pid]["record"]),
            auth["proposals"][pid]["record"],
        ),
    )


def endure(store: Store, session) -> dict:
    """The Endure phase, with the write lock held (D94): commit, in order of
    origination, every proposal that is authorized. A commit refused for its
    content drops the proposal and its approval; a proposal that is not
    authorized waits and logs nothing."""
    close_lapsed(store, clock.grant_now(store.root), session=session)
    committed = []
    dropped = []
    for pid in _by_origination(read_auth(store)):
        auth = read_auth(store)
        prop = auth["proposals"].get(pid)
        if prop is None:
            continue
        now = clock.grant_now(store.root)
        authorized = _authorization(store, auth, prop, now, proposal_id=pid)
        if authorized is None:
            continue
        window = authorized[2]
        try:
            out = _commit(store, pid, session=session)
        except Refused as e:
            auth = read_auth(store)
            auth["proposals"].pop(pid, None)
            auth["approvals"].pop(pid, None)
            write_auth(store, auth)
            fields = {"proposal": pid, "check": e.check, "detail": e.detail}
            log_append(
                store,
                "proposal-dropped",
                rule="OC-001(b)",
                session=session,
                **fields,
            )
            lifecycle._notify(store, sil.owner_binding(store), "commit-refused", fields)
            dropped.append(fields)
            continue
        committed.append(
            {
                "proposal": pid,
                "entry": out["entry"],
                "authorization": out["authorization"],
            }
        )
        if window is not None:
            lifecycle._notify(
                store,
                sil.owner_binding(store),
                "window-commit",
                {"proposal": pid, "grant": window["id"], "entry": out["entry"]},
            )
    return {"committed": committed, "dropped": dropped}


def waiting(store: Store) -> list:
    """The ids of the proposals the Endure phase would commit now, in order
    of origination (D94). Writes and logs nothing: a window past its expiry or
    its budget counts as closed without being closed."""
    auth = read_auth(store)
    now = clock.grant_now(store.root)
    return [
        pid
        for pid in _by_origination(auth)
        if _authorization(store, auth, auth["proposals"][pid], now, proposal_id=pid)
        is not None
    ]
