# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The inference channel: one call, complete, over a declared backend (D87, OC-006)."""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.parse
import urllib.request

from . import config
from .store import MARKER, Store

DEFAULT_ENDPOINT = "http://localhost:11434"
NUM_CTX_DEFAULT = 8192
NUM_CTX_RANGE = (2048, 262144)
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")

_SETTING_KEYS = {"backend", "name", "endpoint", "num_ctx", "digest"}


class ModelError(Exception):
    """A failure of the channel: the network, the time limit, a status other
    than 200, a reply that does not decode or has the wrong shape, or a
    scripted fake that ran out."""


class FakeModel:
    """The declared ``fake`` backend: scripted completions, returned in order."""

    backend = "fake"
    name = "fake"

    def __init__(self, completions):
        self._completions = list(completions)
        self.calls = []

    def complete(self, messages, *, schema=None):
        self.calls.append(messages)
        if not self._completions:
            raise ModelError("the fake model has no completion left")
        return {
            "text": self._completions.pop(0),
            "model": self.name,
            "prompt_eval_count": None,
        }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is a status other than 200, not a second endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener():
    """An opener that uses no proxy of the environment and follows no redirect:
    the endpoint is the local host's, and the context goes nowhere else."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


class OllamaModel:
    """The declared ``ollama`` backend: ``POST <endpoint>/api/chat``."""

    backend = "ollama"

    def __init__(self, name, endpoint, num_ctx, timeout_s):
        self.name = name
        self.endpoint = endpoint
        self.num_ctx = num_ctx
        self.timeout_s = timeout_s

    def _url(self, path):
        return self.endpoint.rstrip("/") + path

    def payload(self, messages, schema):
        """The body of the call: the assembled context, the model name and the
        options; never ``tools``, never ``context``."""
        body = {
            "model": self.name,
            "messages": messages,
            "stream": False,
            "options": {"num_ctx": self.num_ctx},
        }
        if schema is not None:
            body["format"] = schema
        return body

    def complete(self, messages, *, schema=None):
        """Call the model and return once the whole reply has been read."""
        try:
            request = urllib.request.Request(
                self._url("/api/chat"),
                data=json.dumps(self.payload(messages, schema)).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with _opener().open(request, timeout=self.timeout_s) as resp:
                if resp.status != 200:
                    raise ModelError("the model answered status %d" % resp.status)
                reply = json.loads(resp.read().decode("utf-8"))
        except ModelError:
            raise
        except urllib.error.HTTPError as e:
            e.close()
            raise ModelError("the model answered status %d" % e.code) from e
        except (OSError, ValueError, http.client.HTTPException) as e:
            raise ModelError("the call to the model failed: %s" % (e,)) from e
        message = reply.get("message") if isinstance(reply, dict) else None
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ModelError("the reply has no message content")
        return {
            "text": message["content"],
            "model": reply.get("model", self.name),
            "prompt_eval_count": reply.get("prompt_eval_count"),
        }

    def ping(self):
        """A minimal call; raises ``ModelError`` when the model does not answer."""
        self.complete([{"role": "user", "content": "ping"}])

    def digest(self):
        """The weights digest ``/api/tags`` reports for the model, or ``None``
        when it reports none or the server cannot be asked."""
        try:
            with _opener().open(self._url("/api/tags"), timeout=self.timeout_s) as resp:
                if resp.status != 200:
                    return None
                tags = json.loads(resp.read().decode("utf-8"))
            for item in tags["models"]:
                if self.name in (item.get("name"), item.get("model")):
                    found = item.get("digest")
                    return found if isinstance(found, str) else None
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
        except http.client.HTTPException:
            return None
        return None


def local(endpoint):
    """Whether ``endpoint`` is an http(s) URL on the local host (D87)."""
    try:
        parts = urllib.parse.urlsplit(endpoint)
        return parts.scheme in ("http", "https") and parts.hostname in LOCAL_HOSTS
    except (ValueError, TypeError, AttributeError):
        return False


def num_ctx_valid(num_ctx):
    """Whether ``num_ctx`` is an int inside ``NUM_CTX_RANGE``."""
    lo, hi = NUM_CTX_RANGE
    return (
        isinstance(num_ctx, int)
        and not isinstance(num_ctx, bool)
        and lo <= num_ctx <= hi
    )


def _read(store, relpath):
    try:
        return store.read_json(relpath)
    except (OSError, ValueError):
        return None


def setting(store: Store):
    """The model setting in force, or ``None`` (D87): the Operator's, else the
    name first activation recorded on the local endpoint, else none."""
    chosen = _read(store, config.OPERATIONAL)
    chosen = chosen.get("model") if isinstance(chosen, dict) else None
    if (
        isinstance(chosen, dict)
        and set(chosen) == _SETTING_KEYS
        and chosen["backend"] == "ollama"
        and isinstance(chosen["name"], str)
        and isinstance(chosen["endpoint"], str)
        and num_ctx_valid(chosen["num_ctx"])
        and (chosen["digest"] is None or isinstance(chosen["digest"], str))
    ):
        return chosen
    marker = _read(store, MARKER)
    if isinstance(marker, dict) and isinstance(marker.get("model"), str):
        return {
            "backend": "ollama",
            "name": marker["model"],
            "endpoint": DEFAULT_ENDPOINT,
            "num_ctx": NUM_CTX_DEFAULT,
            "digest": None,
        }
    return None
