import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTER = os.path.join(ROOT, "obec-adapter")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fsp-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def p(self, *parts):
        return os.path.join(self.tmp, *parts)


def run_adapter(*args, adapter=ADAPTER):
    """Returns ``(exit_code, parsed_stdout_or_None)``."""
    import json

    proc = subprocess.run(
        [sys.executable, adapter] + list(args), capture_output=True, text=True
    )
    out = json.loads(proc.stdout) if proc.stdout.strip() else None
    return proc.returncode, out
