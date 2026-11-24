"""Tests for organvm_engine.ci.release_rollback (issue #195, step 6).

Pure-helper tests only — the end-to-end rollback (install, uninstall,
reinstall) needs real venvs and is exercised by the release workflow's
``workflow_dispatch`` run and by the PR receipt, not by the unit suite.
"""

from __future__ import annotations

from organvm_engine.ci import release_rollback


def _good_receipt() -> dict:
    return {
        "artifact": "organvm-engine",
        "version": "0.1.0",
        "wheel": "organvm_engine-0.1.0-py3-none-any.whl",
        "sdist": "organvm_engine-0.1.0.tar.gz",
        "steps": [
            {"name": "install candidate wheel", "result": "pass", "detail": ""},
            {"name": "organvm binary gone after uninstall",
             "result": "pass", "detail": ""},
        ],
        "result": "pass",
    }


def test_run_scrubs_pythonpath(monkeypatch) -> None:
    """Child processes must not inherit PYTHONPATH (install honesty).

    Same trap as release_evidence: with PYTHONPATH=src, pip treats
    organvm-engine as already satisfied and the rollback legs would
    silently test the source tree instead of the artifact.
    """
    import os
    import sys

    monkeypatch.setenv("PYTHONPATH", "src")
    result = release_rollback.run([
        sys.executable, "-c",
        "import os; print(os.environ.get('PYTHONPATH', 'ABSENT'))",
    ])
    assert result.stdout.strip() == "ABSENT"
    assert os.environ["PYTHONPATH"] == "src"  # parent untouched


def test_validate_receipt_accepts_good_receipt() -> None:
    """A well-formed passing receipt validates clean."""
    assert release_rollback.validate_receipt(_good_receipt()) == []


def test_validate_receipt_rejects_missing_keys_and_bad_results() -> None:
    """Missing keys, malformed steps and bad results are all flagged."""
    receipt = _good_receipt()
    del receipt["sdist"]
    assert "missing key: sdist" in release_rollback.validate_receipt(receipt)
    receipt = _good_receipt()
    receipt["steps"] = [{"name": "install candidate wheel"}]
    assert any("malformed step" in p
               for p in release_rollback.validate_receipt(receipt))
    receipt = _good_receipt()
    receipt["result"] = "maybe"
    assert any("bad receipt result" in p
               for p in release_rollback.validate_receipt(receipt))
    receipt = _good_receipt()
    receipt["steps"][0]["result"] = "maybe"
    assert any("bad step result" in p
               for p in release_rollback.validate_receipt(receipt))
