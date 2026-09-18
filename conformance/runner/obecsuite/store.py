"""Disposable Entity Stores.

Every test works on a store the runner created and will destroy. The runner
never touches a store it did not make.
"""

import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager


class Stores:
    def __init__(self, adapter, root: str = None, keep: bool = False):
        self.adapter = adapter
        self.root = root or tempfile.mkdtemp(prefix="obec-suite-")
        self.keep = keep
        self._made: list = []

    def path(self, tag: str = "") -> str:
        name = f"store-{tag + '-' if tag else ''}{uuid.uuid4().hex[:8]}"
        p = os.path.join(self.root, name)
        self._made.append(p)
        return p

    def fresh(self, tag: str = "", operator: str = "op-1") -> str:
        """An initialized store. First activation runs once, on an empty
        store, so every test that needs a clean chain starts here."""
        p = self.path(tag)
        os.makedirs(p, exist_ok=True)
        self.adapter.call("lifecycle", "init", store=p, operator=operator)
        return p

    def copy(self, src: str, tag: str = "copy") -> str:
        """A byte-identical copy. Used wherever a test corrupts or
        decommissions, so the original survives for later steps."""
        dst = self.path(tag)
        shutil.copytree(src, dst)
        return dst

    def files(self, store: str) -> list:
        out = []
        for base, _, names in os.walk(store):
            out.extend(os.path.join(base, n) for n in names)
        return sorted(out)

    def flip_bytes(self, store: str, count: int = 8) -> int:
        """Format-independent corruption for step 4.7.

        The runner cannot target a specific artifact in a store whose layout
        it does not know — and that is the point. This check depends on
        nothing the implementation reports about itself.
        """
        touched = 0
        for path in self.files(store):
            if touched >= count:
                break
            try:
                size = os.path.getsize(path)
                if size == 0:
                    continue
                with open(path, "r+b") as fh:
                    fh.seek(size // 2)
                    byte = fh.read(1)
                    if not byte:
                        continue
                    fh.seek(size // 2)
                    fh.write(bytes([byte[0] ^ 0xFF]))
                touched += 1
            except OSError:
                continue
        return touched

    def cleanup(self):
        if self.keep:
            return
        shutil.rmtree(self.root, ignore_errors=True)

    @contextmanager
    def scratch(self, tag: str = "", operator: str = "op-1"):
        store = self.fresh(tag, operator)
        try:
            yield store
        finally:
            pass  # cleanup() removes the whole root at the end of the run
