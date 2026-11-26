"""Release evidence for organvm-engine (issue #195, steps 2-5).

Builds the wheel + sdist from a checkout, inspects the artifacts against the
exclusion list, installs the wheel in a clean venv, and writes the evidence a
clean consumer needs to trust the artifact without the author's workspace:

- ``sbom.json`` — CycloneDX 1.6 inventory of the exact resolved dependency
  set (wheel + runtime deps), with licenses.
- ``sha256sums.txt`` — hashes of wheel, sdist and SBOM.
- ``provenance.json`` — builder, checkout SHA, tool versions, the exclusion
  list applied, and the clean-room checks that passed.

Scope (issue #195 plan, re-verified at main ``1a4692f6`` 2026-11-23): this
module covers plan steps 2-5 only. Step 7 (publication) and step 8 (owner
approval + publish) are NOT done here — #192 is still open, and publishing
is Anthony's call. Two plan premises changed since the plan was written
(2026-11-18, against main ``32c60960``) and the evidence wins:

- ``.github/workflows/release.yml`` now EXISTS (``f7f3bb9``, #98): it builds
  sdist + wheel, attaches them to a GitHub release on ``v*`` tags, and
  smoke-tests the wheel in a clean venv. The plan's "no release workflow
  exists" is stale; this module wires evidence generation into that workflow
  instead of creating a second publish path. No PyPI route exists: PyPI
  returns 404 for ``organvm-engine`` and no tag has ever been pushed.
- #182 (runner admission) is CLOSED, so the CI leg is no longer gated on it.
  The release workflow's build + smoke legs are verifiable by
  ``workflow_dispatch`` right now, without cutting a release.

#180 (which artifact classes need restricted custody) is still OPEN, so the
exclusion list below applies the plan's fallback: every restricted-custody
class is treated as excluded. The list is explicit, with a reason per entry,
and it is recorded in ``provenance.json`` so a #180 verdict can audit it.

One correction to the plan's step-2 wording: the wheel DOES ship the
in-repo ``organvm_engine/ontologia/`` adapter modules and
``pulse/neon_sink.py`` — they are public code whose *external* dependencies
(``organvm-ontologia``, private, not on PyPI; ``psycopg``, the ``neon``
extra) are what the extras gate. What must not leak is the private package
itself, its import name, any bundled ``psycopg``, private corpus data, or
live-custody directories (``legacy/``, ``receipts/``, ``signatures/``).
The clean-room leg verifies the adapters degrade with a diagnostic
(``organvm ontologia status`` exits 1, "not installed", no traceback)
rather than crashing.

Run: ``python -m organvm_engine.ci.release_evidence [--no-build]
[--dist-dir dist] [--out-dir evidence] [--checkout .]``. Exits non-zero
on any failed check, with the failure named on stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# (substring, reason) — a member of the wheel or sdist whose lower-cased
# path contains the substring fails the build. #180 fallback: restricted
# classes are excluded until #180 decides otherwise; the list is recorded
# in provenance.json.
EXCLUSIONS: tuple[tuple[str, str], ...] = (
    ("organvm_ontologia", "private dependency package must never be bundled"),
    ("psycopg", "neon extra dependency must not ship in the default install"),
    ("legacy/", "old packages, not Engine (pre-#195 provenance files)"),
    ("receipts/", "live custody directory, never shipped (#196)"),
    ("signatures/", "live custody directory, never shipped (#196)"),
    (".env", "credentials must never ship"),
    (".pem", "credentials must never ship"),
    (".key", "credentials must never ship"),
    ("credentials", "credentials must never ship"),
)

# Runtime deps of the default install, from pyproject.toml. The evidence
# script asserts the wheel's METADATA requires exactly this set
# unconditionally (extras are conditional and excluded here).
EXPECTED_RUNTIME_DEPS: tuple[str, ...] = (
    "pyyaml>=6.0",
    "jsonschema>=4.20",
    "rfc8785==0.1.4",
)

SBOM_SPEC_VERSION = "1.6"


def fail(message: str) -> "SystemExit":
    """Fail closed: the candidate is unshipped, with the reason on stderr."""
    print(f"release-evidence: FAIL: {message}", file=sys.stderr)
    return SystemExit(1)


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_exclusions(members: list[str], artifact: str) -> list[str]:
    """Return the exclusion violations in an artifact's member list."""
    violations = []
    for member in members:
        lowered = member.lower()
        for pattern, reason in EXCLUSIONS:
            if pattern in lowered:
                violations.append(f"{artifact}: {member} ({reason})")
                break
    return violations


def parse_metadata_requires(metadata_text: str) -> tuple[list[str], list[str]]:
    """Split a wheel METADATA's Requires-Dist into unconditional / extra."""
    unconditional: list[str] = []
    conditional: list[str] = []
    for line in metadata_text.splitlines():
        if not line.startswith("Requires-Dist:"):
            continue
        req = line.split(":", 1)[1].strip()
        if "; extra ==" in req:
            conditional.append(req)
        else:
            unconditional.append(req)
    return unconditional, conditional


def build_sbom(
    *,
    name: str,
    version: str,
    wheel_sha256: str,
    dependencies: list[dict[str, str]],
    tool_versions: dict[str, str],
) -> dict:
    """CycloneDX 1.6 SBOM for the wheel and its resolved runtime deps.

    Each dependency carries name, version, license and purl. Dependency
    hashes are NOT claimed: they are resolved from PyPI at install time and
    are pinned by exact version in the lock the SBOM records; only the wheel
    itself carries a hash, because only it is built here.
    """
    components: list[dict] = [
        {
            "type": "library",
            "bom-ref": f"{name}@{version}",
            "name": name,
            "version": version,
            "licenses": [{"license": {"id": "MIT"}}],
            "hashes": [{"alg": "SHA-256", "content": wheel_sha256}],
            "purl": f"pkg:pypi/{name}@{version}",
        },
    ]
    for dep in dependencies:
        component: dict = {
            "type": "library",
            "bom-ref": f"{dep['name']}@{dep['version']}",
            "name": dep["name"],
            "version": dep["version"],
            "purl": f"pkg:pypi/{dep['name']}@{dep['version']}",
        }
        if dep.get("license"):
            component["licenses"] = [{"license": {"id": dep["license"]}}]
        components.append(component)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": SBOM_SPEC_VERSION,
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": [
                {"vendor": "organvm-engine", "name": "release_evidence",
                 "version": tool_versions.get("release_evidence", "0.1.0")},
            ],
            "component": {
                "type": "application",
                "bom-ref": f"{name}@{version}",
                "name": name,
                "version": version,
            },
        },
        "components": components,
    }


def write_sha256sums(paths: list[Path], out_path: Path) -> None:
    """Write ``<sha256>  <filename>`` lines (GNU sha256sum format)."""
    lines = [f"{sha256_file(p)}  {p.name}\n" for p in paths]
    out_path.write_text("".join(lines), encoding="utf-8")


def verify_sha256sums(sums_path: Path, directory: Path) -> list[str]:
    """Recompute every hash in a sha256sums file; return mismatches."""
    mismatches = []
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        target = directory / name.strip()
        if not target.exists():
            mismatches.append(f"{name.strip()}: missing")
        elif sha256_file(target) != digest.strip():
            mismatches.append(f"{name.strip()}: hash mismatch")
    return mismatches


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    """Run a command, capturing output; never raises on non-zero exit.

    PYTHONPATH is scrubbed from the child environment: a parent run with
    ``PYTHONPATH=src`` would otherwise make the source tree (and its
    ``.egg-info``) visible inside the clean-room venv, so pip would treat
    organvm-engine as already satisfied, skip installing the wheel, and
    the "clean-room" legs would silently test the source tree instead of
    the artifact. The scrub is what makes the clean room clean.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        cmd, capture_output=True, text=True, check=False, env=env, **kwargs,
    )


def build_artifacts(python: str, checkout: Path, dist_dir: Path) -> tuple[Path, Path]:
    """Build wheel + sdist into dist_dir; return their paths."""
    dist_dir.mkdir(parents=True, exist_ok=True)
    result = run([python, "-m", "build", "--outdir", str(dist_dir)], cwd=checkout)
    if result.returncode != 0:
        raise RuntimeError(f"python -m build failed:\n{result.stdout}{result.stderr}")
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError(
            f"expected exactly one wheel and one sdist in {dist_dir}, "
            f"found {len(wheels)} wheel(s), {len(sdists)} sdist(s)",
        )
    return wheels[0], sdists[0]


def inspect_artifacts(wheel: Path, sdist: Path) -> list[str]:
    """Check wheel + sdist members against the exclusion list."""
    violations: list[str] = []
    with zipfile.ZipFile(wheel) as archive:
        violations += check_exclusions(archive.namelist(), f"wheel {wheel.name}")
        metadata = archive.read(
            next(n for n in archive.namelist() if n.endswith("METADATA")),
        ).decode()
    unconditional, _ = parse_metadata_requires(metadata)
    if sorted(unconditional) != sorted(EXPECTED_RUNTIME_DEPS):
        violations.append(
            "wheel METADATA unconditional Requires-Dist "
            f"{sorted(unconditional)} != expected {sorted(EXPECTED_RUNTIME_DEPS)}",
        )
    with tarfile.open(sdist, "r:gz") as archive:
        violations += check_exclusions(archive.getnames(), f"sdist {sdist.name}")
    return violations


def clean_room_checks(
    python: str, wheel: Path, expected_version: str, checkout: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Install the wheel in a fresh venv; return (deps, checks).

    Deps are the installed distributions with name/version/license from
    importlib.metadata. Checks are the clean-room legs of #195 step 4:
    help, version, registry validate on the shipped minimal fixture, and
    the ontologia degrade path (rc 1, diagnostic, no traceback).
    """
    checks: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="oe195-cleanroom-") as tmp:
        venv = Path(tmp) / "venv"
        result = run([python, "-m", "venv", str(venv)])
        if result.returncode != 0:
            raise RuntimeError(f"venv creation failed:\n{result.stdout}{result.stderr}")
        venv_python = venv / "bin" / "python"
        organvm = venv / "bin" / "organvm"
        result = run([str(venv_python), "-m", "pip", "install", "--quiet", str(wheel)])
        if result.returncode != 0:
            raise RuntimeError(f"pip install of wheel failed:\n{result.stdout}{result.stderr}")
        fixture = checkout / "tests" / "fixtures" / "registry-minimal.json"
        legs = [
            ("organvm --help", [str(organvm), "--help"], 0, None),
            (
                "organvm version matches pyproject",
                [str(venv_python), "-c",
                 "import organvm_engine; "
                 f"assert organvm_engine.__version__ == {expected_version!r}, "
                 "organvm_engine.__version__"],
                0,
                None,
            ),
            (
                "registry validate on minimal fixture",
                [str(organvm), "--registry", str(fixture), "registry", "validate"],
                0,
                None,
            ),
            (
                "ontologia degrades without private dep",
                [str(organvm), "--registry", str(fixture), "ontologia", "status"],
                1,
                "not installed",
            ),
        ]
        for name, cmd, expected_rc, must_contain in legs:
            result = run(cmd)
            combined = result.stdout + result.stderr
            ok = result.returncode == expected_rc
            if must_contain is not None:
                ok = ok and must_contain in combined
            if "Traceback" in combined:
                ok = False
            checks.append({
                "name": name,
                "rc": str(result.returncode),
                "expected_rc": str(expected_rc),
                "result": "pass" if ok else "fail",
                "detail": combined.strip().splitlines()[-1][:200]
                if combined.strip() else "",
            })
            if not ok:
                raise RuntimeError(
                    f"clean-room leg failed: {name} "
                    f"(rc {result.returncode}, expected {expected_rc}):\n{combined[:2000]}",
                )
        probe = run([
            str(venv_python), "-c",
            "import importlib.metadata, json; "
            "print(json.dumps(["
            "{'name': d.metadata['Name'], 'version': d.version, "
            "'license': d.metadata.get('License-Expression') "
            "or d.metadata.get('License') or ''} "
            "for d in importlib.metadata.distributions() "
            "if d.metadata['Name'] != 'pip']))",
        ])
        if probe.returncode != 0:
            raise RuntimeError(f"dependency probe failed:\n{probe.stdout}{probe.stderr}")
        deps = json.loads(probe.stdout)
    deps.sort(key=lambda d: d["name"].lower())
    return deps, checks


def git_head(checkout: Path) -> str:
    """Exact checkout SHA the artifacts were built from."""
    result = run(["git", "-C", str(checkout), "rev-parse", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def main(argv: list[str] | None = None) -> int:
    """Generate release evidence; exit 1 (fail closed) on any bad check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path(),
                        help="repo checkout to build from (default: .)")
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"),
                        help="directory holding/ receiving wheel + sdist")
    parser.add_argument("--out-dir", type=Path, default=Path("evidence"),
                        help="directory to write sbom.json, sha256sums.txt, "
                        "provenance.json into")
    parser.add_argument("--no-build", action="store_true",
                        help="use the wheel + sdist already in --dist-dir")
    parser.add_argument("--python", default=sys.executable,
                        help="python to build and clean-room test with")
    args = parser.parse_args(argv)
    checkout = args.checkout.resolve()
    dist_dir = (checkout / args.dist_dir).resolve() \
        if not args.dist_dir.is_absolute() else args.dist_dir
    out_dir = (checkout / args.out_dir).resolve() \
        if not args.out_dir.is_absolute() else args.out_dir
    try:
        if args.no_build:
            wheels = sorted(dist_dir.glob("*.whl"))
            sdists = sorted(dist_dir.glob("*.tar.gz"))
            if len(wheels) != 1 or len(sdists) != 1:
                raise RuntimeError(
                    f"--no-build needs exactly one wheel and one sdist in "
                    f"{dist_dir}, found {len(wheels)}/{len(sdists)}",
                )
            wheel, sdist = wheels[0], sdists[0]
        else:
            wheel, sdist = build_artifacts(args.python, checkout, dist_dir)
        violations = inspect_artifacts(wheel, sdist)
        if violations:
            raise RuntimeError("exclusion violations:\n" + "\n".join(violations))
        version = wheel.name.split("-")[1]
        deps, checks = clean_room_checks(
            args.python, wheel, version, checkout)
        build_result = run([args.python, "-m", "build", "--version"])
        tool_versions = {
            "release_evidence": "0.1.0",
            "build": build_result.stdout.strip(),
            "python": sys.version.split()[0],
        }
        sbom = build_sbom(
            name="organvm-engine", version=version,
            wheel_sha256=sha256_file(wheel), dependencies=deps,
            tool_versions=tool_versions)
        out_dir.mkdir(parents=True, exist_ok=True)
        sbom_path = out_dir / "sbom.json"
        sbom_path.write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
        write_sha256sums([wheel, sdist, sbom_path], out_dir / "sha256sums.txt")
        provenance = {
            "artifact": "organvm-engine",
            "version": version,
            "status": "candidate",
            "published": False,
            "checkout_sha": git_head(checkout),
            "built_at": datetime.now(timezone.utc).isoformat(),
            "builder": tool_versions,
            "clean_room_python": args.python,
            "hashes": {
                "wheel": sha256_file(wheel),
                "sdist": sha256_file(sdist),
                "sbom": sha256_file(sbom_path),
            },
            "exclusions_applied": [
                {"pattern": pattern, "reason": reason}
                for pattern, reason in EXCLUSIONS
            ],
            "exclusions_note": (
                "#180 (restricted-custody classes) is still open, so the "
                "fallback applies: every restricted class is excluded. "
                "In-repo ontologia/neon adapter modules DO ship (public "
                "code); the private organvm-ontologia package and psycopg "
                "do not."
            ),
            "clean_room_checks": checks,
            "dependencies": deps,
            "notes": [
                "No tag has been pushed and no release published for this "
                "version; the candidate is verified, not shipped.",
                "Rollback is tested separately "
                "(organvm_engine.ci.release_rollback); see the PR receipt.",
                "Publication (step 7) and owner approval (step 8) are "
                "deferred: #192 is still open and publishing is "
                "Anthony's call.",
            ],
        }
        (out_dir / "provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        print(f"release-evidence: OK {wheel.name} + {sdist.name} "
              f"({len(deps)} resolved deps, {len(checks)} clean-room legs)")
        return 0
    except RuntimeError as exc:
        print(f"release-evidence: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
