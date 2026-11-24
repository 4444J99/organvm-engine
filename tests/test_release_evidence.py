"""Tests for organvm_engine.ci.release_evidence (issue #195, steps 2-5).

Pure-helper tests only — no builds, no venvs, no network. The end-to-end
path (build + clean-room install) is exercised by the release workflow's
``workflow_dispatch`` run and by the PR receipt, not by the unit suite.
"""

from __future__ import annotations

import hashlib
import json

from organvm_engine.ci import release_evidence


def test_exclusions_catch_private_package_and_custody_dirs() -> None:
    """The #180-fallback exclusion list catches every restricted class."""
    members = [
        "organvm_engine-0.1.0.dist-info/METADATA",
        "organvm_engine/__init__.py",
        # In-repo adapter modules are public code and MUST pass.
        "organvm_engine/ontologia/__init__.py",
        "organvm_engine/pulse/neon_sink.py",
        # These must fail: the private package, its bundled dep, custody.
        "organvm_ontologia/__init__.py",
        "psycopg/__init__.py",
        "legacy/PROVENANCE.md",
        "receipts/2026-01-01.json",
        "signatures/sig.json",
        "config/.env",
        "keys/deploy.pem",
        "keys/deploy.key",
        "credentials.json",
    ]
    violations = release_evidence.check_exclusions(members, "wheel")
    assert len(violations) == 9
    assert all("organvm_engine/ontologia" not in v for v in violations)
    assert all("neon_sink" not in v for v in violations)
    assert any("organvm_ontologia" in v for v in violations)
    assert any("psycopg" in v for v in violations)
    assert any("legacy/" in v for v in violations)
    assert any("receipts/" in v for v in violations)


def test_exclusions_clean_wheel_passes() -> None:
    """A wheel with only public code and the METADATA passes clean."""
    members = [
        "organvm_engine/__init__.py",
        "organvm_engine/ontologia/__init__.py",
        "organvm_engine/pulse/neon_sink.py",
        "organvm_engine-0.1.0.dist-info/METADATA",
        "organvm_engine-0.1.0.dist-info/RECORD",
    ]
    assert release_evidence.check_exclusions(members, "wheel") == []


def test_metadata_requires_split() -> None:
    """Unconditional deps are exactly the public runtime set."""
    metadata = (
        "Name: organvm-engine\nVersion: 0.1.0\n"
        "Requires-Dist: pyyaml>=6.0\n"
        "Requires-Dist: jsonschema>=4.20\n"
        "Requires-Dist: rfc8785==0.1.4\n"
        'Requires-Dist: organvm-ontologia>=0.1.0; extra == "ontologia"\n'
        'Requires-Dist: psycopg[binary]>=3.1; extra == "neon"\n'
    )
    unconditional, conditional = release_evidence.parse_metadata_requires(metadata)
    assert sorted(unconditional) == sorted(release_evidence.EXPECTED_RUNTIME_DEPS)
    assert len(conditional) == 2
    assert all("organvm-ontologia" in c or "psycopg" in c for c in conditional)


def test_sbom_is_cyclonedx_with_wheel_hash_and_dep_licenses() -> None:
    """SBOM shape: CycloneDX 1.6, wheel hashed, deps carry licenses."""
    sbom = release_evidence.build_sbom(
        name="organvm-engine",
        version="0.1.0",
        wheel_sha256="a" * 64,
        dependencies=[
            {"name": "PyYAML", "version": "6.0.4", "license": "MIT"},
            {"name": "jsonschema", "version": "4.26.0", "license": "MIT"},
            {"name": "rfc8785", "version": "0.1.4", "license": ""},
        ],
        tool_versions={"release_evidence": "0.1.0"},
    )
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert json.dumps(sbom)  # serializable
    by_name = {c["name"]: c for c in sbom["components"]}
    assert by_name["organvm-engine"]["hashes"] == [
        {"alg": "SHA-256", "content": "a" * 64},
    ]
    assert by_name["PyYAML"]["licenses"] == [{"license": {"id": "MIT"}}]
    assert by_name["PyYAML"]["purl"] == "pkg:pypi/PyYAML@6.0.4"
    # No license known: no licenses key, and no hash claimed for the dep.
    assert "licenses" not in by_name["rfc8785"]
    assert "hashes" not in by_name["rfc8785"]


def test_run_scrubs_pythonpath(monkeypatch) -> None:
    """Child processes must not inherit PYTHONPATH (clean-room honesty).

    With PYTHONPATH=src, the source tree's .egg-info makes pip treat
    organvm-engine as already satisfied, so the wheel never installs
    and the clean-room legs silently test the source tree.
    """
    import os
    import sys

    monkeypatch.setenv("PYTHONPATH", "src")
    result = release_evidence.run([
        sys.executable, "-c",
        "import os; print(os.environ.get('PYTHONPATH', 'ABSENT'))",
    ])
    assert result.stdout.strip() == "ABSENT"
    assert os.environ["PYTHONPATH"] == "src"  # parent untouched


def test_sha256sums_round_trip_and_mismatch(tmp_path) -> None:
    """sha256sums write + verify passes, then catches tampering."""
    target = tmp_path / "organvm_engine-0.1.0-py3-none-any.whl"
    target.write_bytes(b"fake wheel bytes")
    sums = tmp_path / "sha256sums.txt"
    release_evidence.write_sha256sums([target], sums)
    assert release_evidence.verify_sha256sums(sums, tmp_path) == []
    assert sums.read_text().split()[0] == hashlib.sha256(b"fake wheel bytes").hexdigest()
    target.write_bytes(b"tampered")
    assert release_evidence.verify_sha256sums(sums, tmp_path) == [
        "organvm_engine-0.1.0-py3-none-any.whl: hash mismatch",
    ]
    target.unlink()
    assert release_evidence.verify_sha256sums(sums, tmp_path) == [
        "organvm_engine-0.1.0-py3-none-any.whl: missing",
    ]
