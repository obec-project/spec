# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The execution path (EXEC): the native primitives, inside the workspace and
outside the store (OC-008, D15)."""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import selectors
import signal
import socket
import ssl
import subprocess
import threading
import time
from urllib.parse import urljoin, urlsplit

from . import __version__, chain, config, ledger, lifecycle, monitor, sil, vital
from . import manifest as skill_manifest
from .digest import sha256, sha256_file
from .sil import Refused, log_append
from .store import DOMAIN_ENTRY, GuardError, Store, remove_host_tree, write_host_file
from .verify import Finding

OUTPUT_CAP = 1 << 16  # the most bytes kept of each output stream of a skill
FETCH_CAP = 1 << 20  # the most bytes of a fetched body kept (D75)
MAX_REDIRECTS = 5  # redirects a fetch follows, each a new target (D75)
# seconds past timeout_s by which the launched process must be reaped (D72)
WATCHDOG_GRACE_S = 5


def workspace_of(store: Store):
    """The workspace the Operator declared (OC-008(a)), or ``None``."""
    try:
        data = store.read_json(config.OPERATIONAL)
    except (FileNotFoundError, ValueError):
        return None
    ws = data.get("workspace") if isinstance(data, dict) else None
    return ws if isinstance(ws, str) else None


def _inside(path, root):
    return path == root or path.startswith(root + os.sep)


def _refuse(store, op, target, check, rule, detail, **extra):
    rec = log_append(
        store,
        "refusal",
        rule=rule,
        check=check,
        detail=detail,
        op=op,
        target=target,
        **extra,
    )
    return Refused(check, rule, detail, [rec])


def boundary(store, op, target):
    """The workspace boundary, the first check of every act on the host
    (OC-008(a)(b), step 8.6). Returns ``(real, rel)``: the resolved target and
    its path relative to the workspace. It runs before the session check and
    before the Vital Check."""
    ws = workspace_of(store)
    if ws is None:
        raise _refuse(
            store,
            op,
            target,
            "workspace-boundary",
            "OC-008(a)",
            "no workspace is declared",
        )
    if not isinstance(target, str) or not target:
        raise _refuse(store, op, target, "workspace-boundary", "OC-008(a)", "no target")
    ws_real = os.path.realpath(ws)
    store_real = os.path.realpath(store.root)
    path = target if os.path.isabs(target) else os.path.join(ws_real, target)
    real = os.path.realpath(path)
    if _inside(real, store_real):
        raise _refuse(
            store,
            op,
            target,
            "workspace-boundary",
            "OC-008(b)",
            "%r is inside the Entity Store" % target,
        )
    if not _inside(real, ws_real):
        raise _refuse(
            store,
            op,
            target,
            "workspace-boundary",
            "OC-008(a)",
            "%r resolves outside the workspace" % target,
        )
    rel = os.path.relpath(real, ws_real).replace(os.sep, "/")
    return real, rel


def _executed(store, session, op, rel, **fields):
    return log_append(
        store,
        "execution",
        rule="OC-008(d)",
        session=session,
        op=op,
        target=rel,
        **fields,
    )


def _failed(store, session, op, rel, error):
    rec = _executed(store, session, op, rel, outcome="failed", error=error)
    return Refused(
        "execution", "OC-008(d)", "%s on %s failed: %s" % (op, rel, error), [rec]
    )


def file_read(root, target):
    """Read a file inside the workspace. Returns its content, size and digest;
    the adapter reports only the size and the digest (D15)."""
    store = Store(root)
    with store.write_lock():
        real, rel = boundary(store, "file_read", target)
        session = vital.require_entity_session(root, "file_read")
        try:
            with open(real, "rb") as f:
                data = f.read()
        except OSError as e:
            raise _failed(store, session, "file_read", rel, str(e))
        digest = sha256(data)
        rec = _executed(
            store,
            session,
            "file_read",
            rel,
            outcome="done",
            size=len(data),
            sha256=digest,
        )
        return {
            "data": data,
            "size": len(data),
            "sha256": digest,
            "target": rel,
            "log_records": [rec],
        }


def file_write(root, target, data, *, intent):
    """Write ``data`` to a file inside the workspace, under an Action Ledger
    entry opened before the write and resolved after it (OP-015, OC-008(d))."""
    store = Store(root)
    with store.write_lock():
        real, rel = boundary(store, "file_write", target)
        session = vital.require_entity_session(root, "file_write")
        entry = ledger.open_entry(
            store, op="file_write", target=rel, intent=intent, session=session
        )
        try:
            write_host_file(real, data, stores=(store.root,))
        except (OSError, GuardError) as e:
            ledger.resolve_entry(store, entry, "failed", session=session, error=str(e))
            raise _failed(store, session, "file_write", rel, str(e))
        ledger.resolve_entry(store, entry, "done", session=session)
        rec = _executed(
            store,
            session,
            "file_write",
            rel,
            outcome="done",
            size=len(data),
            sha256=sha256(data),
            ledger=entry,
        )
        return {
            "size": len(data),
            "sha256": sha256(data),
            "target": rel,
            "ledger": entry,
            "log_records": [rec],
        }


def file_list(root, target):
    """List the names in a directory inside the workspace, sorted."""
    store = Store(root)
    with store.write_lock():
        real, rel = boundary(store, "file_list", target)
        session = vital.require_entity_session(root, "file_list")
        try:
            names = sorted(os.listdir(real))
        except OSError as e:
            raise _failed(store, session, "file_list", rel, str(e))
        rec = _executed(
            store, session, "file_list", rel, outcome="done", count=len(names)
        )
        return {"entries": names, "target": rel, "log_records": [rec]}


def _resolve(host, port):
    """The addresses ``host`` resolves to, in the resolver's order, without
    repeats (D75). A seam: the tests replace it."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(info[4][0] for info in infos))


def _connect(address, port, host, tls, timeout):
    """A connection to ``address``, wrapped in TLS checked against ``host`` when
    ``tls`` (D75). A seam: the tests replace it."""
    sock = socket.create_connection((address, port), timeout=timeout)
    if not tls:
        return sock
    try:
        return ssl.create_default_context().wrap_socket(sock, server_hostname=host)
    except BaseException:
        sock.close()
        raise


def _public(address):
    """Whether ``address`` is one a fetch may reach: global and not multicast
    (D75)."""
    ip = ipaddress.ip_address(address)
    return ip.is_global and not ip.is_multicast


def _network_boundary(store, op, url):
    """The boundary of a network target (OC-008(a), D74, D75). Returns
    ``(scheme, host, port, path, key)``, where ``key`` is the allowlist entry
    the target falls under (D76). Called with the write lock held; every check
    runs before any name is resolved."""

    def refuse(detail):
        return _refuse(store, op, url, "workspace-boundary", "OC-008(a)", detail)

    if not isinstance(url, str) or any(ord(c) < 0x21 or ord(c) == 0x7F for c in url):
        raise refuse("%r is not a URL without spaces or control characters" % (url,))
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http"):
        raise refuse("%r is not https or http" % (parts.scheme,))
    if parts.username is not None or parts.password is not None:
        raise refuse("credentials in the URL")
    default = 443 if parts.scheme == "https" else 80
    try:
        port = parts.port
    except ValueError:
        raise refuse("the port of %r is not a number in range" % (url,))
    if port is None:
        port = default
    elif port != default:
        raise refuse("port %s is not the scheme's" % (port,))
    host = parts.hostname
    if not host:
        raise refuse("%r has no host name" % (url,))
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise refuse("%r is an address, not a name" % (host,))
    key = host if parts.scheme == "https" else "http://" + host
    if not DOMAIN_ENTRY.match(key):
        raise refuse("%r is not a domain" % (key,))
    try:
        head = sil.read_head(store)
        rules = store.read_json(chain.gen_relpath(head["entry"]) + "/rules.json")
    except (OSError, ValueError, KeyError):
        rules = None
    domains = rules.get("domains") if isinstance(rules, dict) else None
    entry = domains.get(key) if isinstance(domains, dict) else None
    verdict = entry.get("rule") if isinstance(entry, dict) else None
    if verdict == "deny":
        raise refuse("%r is denied" % (key,))
    if verdict != "allow":
        raise _refuse(
            store,
            op,
            url,
            "workspace-boundary",
            "OC-008(a)",
            "%r is outside the declared territory" % (key,),
            reason="hold",
        )
    path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
    return parts.scheme, host, port, path, key


def http_fetch(root, url):
    """Read ``url`` over HTTP or HTTPS from a declared, public destination (OC-008(a),
    D74, D75). The body is kept up to ``FETCH_CAP``; reaching ``http_timeout_s`` is
    the result ``timeout``. Returns the status, the content type, the final URL and
    the body with its size and digest; the adapter reports only the size and the
    digest (D15)."""
    store = Store(root)
    with store.write_lock():
        info = _network_boundary(store, "http_fetch", url)
        session = vital.require_entity_session(root, "http_fetch")
        timeout = config.value(store, "http_timeout_s")
    deadline = time.monotonic() + timeout
    hops = []
    current = url
    status = content_type = None
    body = b""
    truncated = False
    outcome = "done"
    conn = resp = None
    try:
        while True:
            scheme, host, port, path, _key = info
            if time.monotonic() >= deadline:
                outcome = "timeout"
                break
            try:
                addresses = _resolve(host, port)
            except OSError as e:
                with store.write_lock():
                    raise _failed(store, session, "http_fetch", url, str(e))
            if not addresses or not all(_public(a) for a in addresses):
                with store.write_lock():
                    raise _refuse(
                        store,
                        "http_fetch",
                        current,
                        "workspace-boundary",
                        "OC-008(a)",
                        "%r resolves to an address outside the territory: %s"
                        % (host, ", ".join(addresses) or "nothing"),
                    )
            tls = scheme == "https"
            remaining = deadline - time.monotonic()
            try:
                sock = _connect(addresses[0], port, host, tls, remaining)
                connect_class = (
                    http.client.HTTPSConnection if tls else http.client.HTTPConnection
                )
                conn = connect_class(host, port, timeout=remaining)
                conn.sock = sock
                conn.request(
                    "GET",
                    path,
                    headers={
                        "User-Agent": "fsp/" + __version__,
                        "Accept": "*/*",
                        "Accept-Encoding": "identity",
                        "Connection": "close",
                    },
                )
                resp = conn.getresponse()
                status = resp.status
                content_type = resp.getheader("Content-Type")
                hops.append({"url": current, "status": status})
                location = resp.getheader("Location")
                if status in (301, 302, 303, 307, 308) and location:
                    resp.close()
                    conn.close()
                    resp = conn = None
                    if len(hops) > MAX_REDIRECTS:
                        with store.write_lock():
                            raise _failed(
                                store,
                                session,
                                "http_fetch",
                                url,
                                "more than %d redirects" % MAX_REDIRECTS,
                            )
                    current = urljoin(current, location)
                    with store.write_lock():
                        info = _network_boundary(store, "http_fetch", current)
                    continue
                # the response closes its socket once the body is complete
                while not resp.isclosed():
                    if time.monotonic() >= deadline:
                        outcome = "timeout"
                        break
                    sock.settimeout(max(0.01, deadline - time.monotonic()))
                    chunk = resp.read1(65536)
                    if not chunk:
                        break
                    room = FETCH_CAP - len(body)
                    body += chunk[:room]
                    if len(chunk) > room:
                        truncated = True
                        break
                break
            except TimeoutError:
                outcome = "timeout"
                break
            except (OSError, http.client.HTTPException, ValueError) as e:
                with store.write_lock():
                    raise _failed(store, session, "http_fetch", url, str(e))
    finally:
        if resp is not None:
            resp.close()
        if conn is not None:
            conn.close()
    digest = sha256(body)
    with store.write_lock():
        rec = _executed(
            store,
            session,
            "http_fetch",
            url,
            outcome=outcome,
            status=status,
            final_url=current,
            hops=hops,
            size=len(body),
            sha256=digest,
            truncated=truncated,
        )
    return {
        "status": status,
        "content_type": content_type,
        "url": current,
        "data": body,
        "size": len(body),
        "sha256": digest,
        "truncated": truncated,
        "outcome": outcome,
        "log_records": [rec],
    }


def _end_group(pid):
    """Kill the process group ``pid`` leads, whatever it still holds (D51)."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


# The process groups of the skills running now, which a suspend ends (D92).
_RUNNING = set()
_RUNNING_LOCK = threading.Lock()


def end_running() -> int:
    """End the group of every skill running and forget them (D92, D51).
    Returns how many."""
    with _RUNNING_LOCK:
        pids = list(_RUNNING)
        _RUNNING.clear()
    for pid in pids:
        _end_group(pid)
    return len(pids)


def _run(proc, timeout, launch):
    """Read the output of ``proc`` as it arrives, keeping ``OUTPUT_CAP`` bytes of
    each stream, until ``launch + timeout``; end its group if that comes first,
    then wait for the reaping by ``launch + timeout + WATCHDOG_GRACE_S`` (D72).
    Returns ``(out, err, outcome, reaped)``."""
    deadline = launch + timeout
    watchdog = deadline + WATCHDOG_GRACE_S
    bufs = {proc.stdout: bytearray(), proc.stderr: bytearray()}
    sel = selectors.DefaultSelector()
    timed_out = False
    try:
        for f in bufs:
            sel.register(f, selectors.EVENT_READ)
        while sel.get_map():
            left = deadline - time.monotonic()
            if left <= 0:
                timed_out = True
                break
            for key, _ in sel.select(left):
                f = key.fileobj
                chunk = os.read(f.fileno(), 65536)
                if not chunk:
                    sel.unregister(f)
                    continue
                buf = bufs[f]
                buf += chunk[: OUTPUT_CAP - len(buf)]
        if not timed_out:
            try:
                proc.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
        if timed_out:
            _end_group(proc.pid)
    finally:
        sel.close()
        proc.stdout.close()
        proc.stderr.close()
    if proc.returncode is None:
        try:
            proc.wait(timeout=max(0, watchdog - time.monotonic()))
            reaped = True
        except subprocess.TimeoutExpired:
            reaped = False
    else:
        reaped = True
    if timed_out:
        outcome = "timeout"
    else:
        outcome = "done" if proc.returncode == 0 else "failed"
    return bytes(bufs[proc.stdout]), bytes(bufs[proc.stderr]), outcome, reaped


def invoke_skill(root, name, target=None, args=None):
    """Invoke the skill ``name`` from a verified copy, under the Operator's rule,
    its process group ended with it, with its typed arguments (OC-008, D51, D16,
    D71)."""
    op = "invoke-skill"
    store = Store(root)
    copy = None
    try:
        with store.write_lock():
            real_t, rel_t = boundary(store, op, target if target is not None else ".")
            marked = {}
            if isinstance(args, dict):
                for k in sorted(args, key=str):
                    if skill_manifest.is_marked_path(args[k]):
                        marked[k] = boundary(store, op, args[k]["path"])[0]
            ws_real = os.path.realpath(workspace_of(store))
            session = vital.require_entity_session(root, op)

            try:
                index = store.read_json(lifecycle.INDEX)
            except (OSError, ValueError):
                raise _refuse(
                    store,
                    op,
                    name,
                    "skill-index",
                    "OC-008(c)",
                    "the skill index cannot be read",
                )
            entry = next((s for s in index["skills"] if s["name"] == name), None)
            if entry is None:
                raise _refuse(
                    store,
                    op,
                    name,
                    "skill-index",
                    "OC-008(c)",
                    "%r is not in the skill index" % name,
                )

            skill_dir = chain.gen_relpath(index["generation"]) + "/skills/" + name
            prefix = "skills/%s/" % name
            expected = {f["path"][len(prefix) :]: f["sha256"] for f in entry["files"]}
            committed = set()
            base = store.path(skill_dir)
            for dirpath, _dirs, files in os.walk(base):
                for f in files:
                    full = os.path.join(dirpath, f)
                    committed.add(os.path.relpath(full, base).replace(os.sep, "/"))
            if committed != set(expected):
                raise _refuse(
                    store,
                    op,
                    name,
                    "skill-manifest",
                    "OC-008(c)",
                    "the files of %r are not those the index admitted" % name,
                )
            try:
                copy = store.copy_out(skill_dir, sorted(expected))
            except (OSError, GuardError) as e:
                raise _refuse(
                    store,
                    op,
                    name,
                    "skill-manifest",
                    "OC-008(c)",
                    "%r cannot be copied: %s" % (name, e),
                )
            for f in sorted(expected):
                if sha256_file(os.path.join(copy, *f.split("/"))) != expected[f]:
                    raise _refuse(
                        store,
                        op,
                        name,
                        "skill-manifest",
                        "OC-008(c)",
                        "%s of %r changed since the index admitted it" % (f, name),
                    )
            try:
                with open(os.path.join(copy, "manifest.json"), "rb") as fh:
                    manifest = json.load(fh)
            except (OSError, ValueError):
                found = ["manifest.json cannot be read"]
            else:
                found = skill_manifest.problems(manifest, name)
            if found:
                raise _refuse(
                    store, op, name, "skill-manifest", "OC-008(c)", "; ".join(found)
                )
            for t in manifest["targets"]:
                boundary(store, op, t)

            schema = manifest.get("args", {})
            found = skill_manifest.invocation_problems(schema, args)
            if found:
                raise _refuse(
                    store, op, name, "skill-args", "OC-008(c)", "; ".join(found)
                )

            digest = skill_manifest.skill_digest(entry["files"])
            try:
                rules = store.read_json(
                    chain.gen_relpath(sil.read_head(store)["entry"]) + "/rules.json"
                )
            except (OSError, ValueError):
                rules = None
            if not isinstance(rules, dict):
                raise _refuse(
                    store,
                    op,
                    name,
                    "operator-rule",
                    "OC-008(c)",
                    "the Operator's rules cannot be read",
                )
            skills = rules.get("skills")
            rule = skills.get(name) if isinstance(skills, dict) else None
            if isinstance(rule, dict) and rule.get("rule") == "deny":
                raise _refuse(
                    store,
                    op,
                    name,
                    "operator-rule",
                    "OC-008(c)",
                    "%r is denied by the Operator's rule" % name,
                    reason="deny",
                    skill=name,
                    digest=digest,
                )
            if not (
                isinstance(rule, dict)
                and rule.get("rule") == "allow"
                and rule.get("digest") == digest
            ):
                if rules.get("default") == "deny":
                    raise _refuse(
                        store,
                        op,
                        name,
                        "operator-rule",
                        "OC-008(c)",
                        "%r is denied by the Operator's default rule" % name,
                        reason="deny",
                        skill=name,
                        digest=digest,
                    )
                raise _refuse(
                    store,
                    op,
                    name,
                    "operator-rule",
                    "OC-008(c)",
                    "%r at %s is held: the Operator's rules do not allow it, "
                    "and no one can answer" % (name, digest),
                    reason="hold",
                    skill=name,
                    digest=digest,
                )

            values = {"skill": copy, "workspace": ws_real, "target": real_t}
            for k, spec in schema.items():
                if spec["type"] == "path":
                    values["args." + k] = marked[k]
                elif spec["type"] == "boolean":
                    values["args." + k] = "true" if args[k] else "false"
                else:
                    values["args." + k] = str(args[k])
            argv = [skill_manifest.fill(a, values) for a in manifest["argv"]]
            timeout = manifest["timeout_s"]
            entry_id = None
            if manifest["irreversible"]:
                entry_id = ledger.open_entry(
                    store,
                    op=op,
                    target=rel_t,
                    intent="skill %s" % name,
                    session=session,
                )
            before = monitor.picture(store)

        env = {
            "PATH": os.environ.get("PATH", os.defpath),
            "HOME": ws_real,
            "LANG": "C.UTF-8",
        }
        launch_error = None
        try:
            proc = subprocess.Popen(
                argv,
                cwd=ws_real,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as e:
            launch_error = str(e)
        else:
            with _RUNNING_LOCK:
                _RUNNING.add(proc.pid)
            launch = time.monotonic()
            try:
                out, err, outcome, reaped = _run(proc, timeout, launch)
            finally:
                _end_group(proc.pid)
                with _RUNNING_LOCK:
                    _RUNNING.discard(proc.pid)

        with store.write_lock():
            if launch_error is not None:
                if entry_id is not None:
                    ledger.resolve_entry(
                        store, entry_id, "failed", session=session, error=launch_error
                    )
                raise _failed(store, session, op, rel_t, launch_error)
            findings = monitor.compare(store, before)
            if entry_id is not None:
                ledger.resolve_entry(
                    store, entry_id, outcome, session=session, exit=proc.returncode
                )
            rec = _executed(
                store,
                session,
                op,
                rel_t,
                skill=name,
                digest=digest,
                outcome=outcome,
                exit=proc.returncode,
                ledger=entry_id,
                args=args if args is not None else {},
            )
            critical = list(findings)
            if not reaped:
                critical.append(
                    Finding(
                        "watchdog",
                        skill_dir,
                        "exec",
                        {"pid": proc.pid, "deadline_s": timeout + WATCHDOG_GRACE_S},
                    )
                )
            if critical:
                vital._critical(store, session, critical)
            return {
                "skill": name,
                "outcome": outcome,
                "exit": proc.returncode,
                "stdout": out[:OUTPUT_CAP],
                "stderr": err[:OUTPUT_CAP],
                "log_records": [rec],
            }
    finally:
        if copy is not None:
            remove_host_tree(copy, stores=(store.root,))


def attempt_file_write(store: Store, cls, target):
    """file_write's attempted write: a host operation writes no content class
    of the store, so it refuses every one (D68)."""
    raise sil.refuse_attempt(
        store,
        "sole-writer",
        "file_write writes the workspace, no content class of the store",
        via="file_write",
        content_class=cls,
        target=target,
    )


def attempt_file_read(store: Store, cls, target):
    """file_read's attempted write: a host operation writes no content class
    of the store, so it refuses every one (D68)."""
    raise sil.refuse_attempt(
        store,
        "sole-writer",
        "file_read reads the workspace and writes no content class of the store",
        via="file_read",
        content_class=cls,
        target=target,
    )


def attempt_file_list(store: Store, cls, target):
    """file_list's attempted write: a host operation writes no content class
    of the store, so it refuses every one (D68)."""
    raise sil.refuse_attempt(
        store,
        "sole-writer",
        "file_list lists the workspace and writes no content class of the store",
        via="file_list",
        content_class=cls,
        target=target,
    )


def attempt_http_fetch(store: Store, cls, target):
    """http_fetch's attempted write: a fetch reads the network and writes no
    content class of the store, so it refuses every one (D68)."""
    raise sil.refuse_attempt(
        store,
        "sole-writer",
        "http_fetch reads the network and writes no content class of the store",
        via="http_fetch",
        content_class=cls,
        target=target,
    )


def attempt_invoke_skill(store: Store, cls, target):
    """invoke-skill's attempted write: a skill runs in the workspace and writes
    no content class of the store, so it refuses every one (D68)."""
    raise sil.refuse_attempt(
        store,
        "sole-writer",
        "invoke-skill runs in the workspace and writes no content class of the store",
        via="invoke-skill",
        content_class=cls,
        target=target,
    )
