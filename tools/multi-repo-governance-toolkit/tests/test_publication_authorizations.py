import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate-publication-authorizations.py"
REVISION = "a" * 40

def run(tmp_path, records, *args):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"default": "deny", "authorizations": records}), encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), "--ledger", str(ledger), *args], text=True, capture_output=True, check=False)

def record(**overrides):
    now = dt.datetime.now(dt.timezone.utc)
    value = {
        "id": "PUB-0001", "repository_id": "123", "formation_id": "FORM-001",
        "revision": REVISION, "paths": ["docs/public/**"], "surface": "documentation",
        "destination": "example.invalid/docs", "license": "All rights reserved",
        "rights_authority": "owner", "approved_by": "owner",
        "benefit": "Customer evaluation without source disclosure",
        "approved_at": (now - dt.timedelta(days=1)).isoformat(),
        "expires_at": (now + dt.timedelta(days=1)).isoformat(), "status": "approved",
    }
    value.update(overrides)
    return value

class PublicationAuthorizationTests(unittest.TestCase):
    def invoke(self, records, *args):
        with tempfile.TemporaryDirectory() as directory:
            return run(Path(directory), records, *args)
    def test_empty_ledger_is_valid_but_denies_publication(self):
        self.assertEqual(self.invoke([]).returncode, 0)
        self.assertEqual(self.invoke([], "--repository-id", "123", "--revision", REVISION, "--surface", "documentation", "--path", "docs/public/index.md").returncode, 3)
    def test_exact_authorization_allows_bounded_path(self):
        self.assertEqual(self.invoke([record()], "--repository-id", "123", "--revision", REVISION, "--surface", "documentation", "--path", "docs/public/index.md").returncode, 0)
    def test_wrong_revision_and_expired_record_are_denied(self):
        self.assertEqual(self.invoke([record()], "--repository-id", "123", "--revision", "b" * 40, "--surface", "documentation", "--path", "docs/public/index.md").returncode, 3)
        expired = record(expires_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat())
        self.assertEqual(self.invoke([expired], "--repository-id", "123", "--revision", REVISION, "--surface", "documentation", "--path", "docs/public/index.md").returncode, 3)
    def test_unbounded_authorization_is_invalid(self):
        self.assertEqual(self.invoke([record(paths=["**"])]).returncode, 2)

if __name__ == "__main__":
    unittest.main()
