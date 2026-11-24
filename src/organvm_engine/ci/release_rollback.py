"""Tested rollback for an organvm-engine release candidate (#195, step 6).

A documented rollback is not a tested one. This module installs the
candidate wheel in a fresh venv, verifies it, uninstalls it, verifies the
uninstall actually removed it, then reinstalls from the sdist and verifies
the same version and behaviour return. The receipt records every step with
its exit code, so a reviewer can see the rollback rather than take it on
faith.

First-release scope: no earlier version of organvm-engine has ever been
published (PyPI 404s for the project; no tag exists), so there is no
previous version to downgrade TO. The testable rollback for 0.1.0 is
therefore uninstall + reinstall from the sdist, asserting the installed
tree returns to the same version and the same passing checks. When a
0.1.1 candidate exists, the downgrade leg (install 0.1.1, roll back to
the installed 0.1.0 wheel, verify) becomes the stronger form; this module
takes ``--previous-wheel`` for exactly that leg when one exists.

Run: ``python -m organvm_engine.ci.release_rollback --wheel dist/*.whl
--sdist dist/*.tar.gz --version 0.1.0 [--previous-wheel dist/*.whl]
[--checkout .] [--out-dir evidence]``. Exits non-zero on any failed
step, with the failure named on stderr. The receipt is written to
``<out-dir>/rollback.json`` (and printed) on success.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    """Run a command, capturing output; never raises on non-zero exit.

    PYTHONPATH is scrubbed from the child environment: a parent run with
    ``PYTHONPATH=src`` would otherwise make the source tree (and its
    ``.egg-info``) visible inside the test venv, so pip would treat
    organvm-engine as already satisfied, skip installing the wheel, and
    the rollback legs would silently test the source tree instead of the
    artifact. The scrub is what makes the test venv a real install.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        cmd, capture_output=True, text=True, check=False, env=env, **kwargs,
    )


def installed_version(venv_python: Path) -> str | None:
    """Version of the installed organvm-engine, or None if not installed."""
    result = run([
        str(venv_python), "-c",
        "import importlib.metadata\n"
        "print(importlib.metadata.version('organvm-engine'))",
    ])
    return result.stdout.strip() if result.returncode == 0 else None


def verify_installed(
    venv: Path, expected_version: str, checkout: Path,
) -> list[dict[str, str]]:
    """Checks that must pass on every installed state of the candidate."""
    venv_python = venv / "bin" / "python"
    organvm = venv / "bin" / "organvm"
    fixture = checkout / "tests" / "fixtures" / "registry-minimal.json"
    checks: list[dict[str, str]] = []
    version = installed_version(venv_python)
    checks.append({
        "name": "installed version matches candidate",
        "result": "pass" if version == expected_version else "fail",
        "detail": f"installed={version!r} expected={expected_version!r}",
    })
    for name, cmd, expected_rc in [
        ("organvm --help", [str(organvm), "--help"], 0),
        (
            "registry validate on minimal fixture",
            [str(organvm), "--registry", str(fixture), "registry", "validate"],
            0,
        ),
    ]:
        result = run(cmd)
        combined = result.stdout + result.stderr
        ok = result.returncode == expected_rc and "Traceback" not in combined
        checks.append({
            "name": name,
            "result": "pass" if ok else "fail",
            "detail": f"rc={result.returncode} expected={expected_rc}",
        })
    return checks


def validate_receipt(receipt: dict) -> list[str]:
    """Shape check for a rollback receipt; returns the problems found."""
    problems: list[str] = []
    for key in ("version", "wheel", "sdist", "steps", "result"):
        if key not in receipt:
            problems.append(f"missing key: {key}")
    for step in receipt.get("steps", []):
        if "name" not in step or "result" not in step:
            problems.append(f"malformed step: {step!r}")
        if step.get("result") not in ("pass", "fail"):
            problems.append(f"bad step result: {step!r}")
    if receipt.get("result") not in ("pass", "fail"):
        problems.append(f"bad receipt result: {receipt.get('result')!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    """Run the rollback test; exit 1 (fail closed) on any failed step."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True,
                        help="candidate wheel to install first")
    parser.add_argument("--sdist", type=Path, required=True,
                        help="sdist to reinstall from after uninstall")
    parser.add_argument("--version", required=True,
                        help="expected candidate version (e.g. 0.1.0)")
    parser.add_argument("--previous-wheel", type=Path, default=None,
                        help="earlier wheel to downgrade to, when one exists")
    parser.add_argument("--checkout", type=Path, default=Path(),
                        help="repo checkout (for the minimal registry fixture)")
    parser.add_argument("--out-dir", type=Path, default=Path("evidence"),
                        help="directory to write rollback.json into")
    parser.add_argument("--python", default=sys.executable,
                        help="python to build the test venvs with")
    args = parser.parse_args(argv)
    checkout = args.checkout.resolve()
    steps: list[dict[str, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> bool:
        steps.append({"name": name, "result": "pass" if ok else "fail",
                      "detail": detail})
        return ok

    try:
        with tempfile.TemporaryDirectory(prefix="oe195-rollback-") as tmp:
            venv = Path(tmp) / "venv"
            result = run([args.python, "-m", "venv", str(venv)])
            if result.returncode != 0:
                raise RuntimeError(f"venv creation failed:\n{result.stderr}")
            venv_python = venv / "bin" / "python"
            result = run([str(venv_python), "-m", "pip", "install",
                          "--quiet", str(args.wheel)])
            if not record("install candidate wheel",
                          result.returncode == 0,
                          result.stderr.strip().splitlines()[-1][:200]
                          if result.stderr.strip() else ""):
                raise RuntimeError("install of candidate wheel failed")
            for check in verify_installed(venv, args.version, checkout):
                record(f"verify after install: {check['name']}",
                       check["result"] == "pass", check["detail"])
            result = run([str(venv_python), "-m", "pip", "uninstall",
                          "--quiet", "-y", "organvm-engine"])
            if not record("uninstall candidate",
                          result.returncode == 0,
                          result.stderr.strip().splitlines()[-1][:200]
                          if result.stderr.strip() else ""):
                raise RuntimeError("uninstall failed")
            gone_binary = shutil.which("organvm", path=str(venv / "bin")) is None
            gone_import = installed_version(venv_python) is None
            record("organvm binary gone after uninstall", gone_binary)
            record("organvm_engine import gone after uninstall", gone_import)
            if args.previous_wheel is not None:
                result = run([str(venv_python), "-m", "pip", "install",
                              "--quiet", str(args.previous_wheel)])
                if not record("downgrade to previous wheel",
                              result.returncode == 0):
                    raise RuntimeError("downgrade install failed")
                previous_version = installed_version(venv_python)
                record("previous version installed after downgrade",
                       previous_version is not None
                       and previous_version != args.version,
                       f"installed={previous_version!r}")
            result = run([str(venv_python), "-m", "pip", "install",
                          "--quiet", str(args.sdist)])
            if not record("reinstall from sdist",
                          result.returncode == 0,
                          result.stderr.strip().splitlines()[-1][:200]
                          if result.stderr.strip() else ""):
                raise RuntimeError("reinstall from sdist failed")
            for check in verify_installed(venv, args.version, checkout):
                record(f"verify after reinstall: {check['name']}",
                       check["result"] == "pass", check["detail"])
        failed = [s for s in steps if s["result"] == "fail"]
        receipt = {
            "artifact": "organvm-engine",
            "version": args.version,
            "wheel": args.wheel.name,
            "sdist": args.sdist.name,
            "previous_wheel": args.previous_wheel.name
            if args.previous_wheel is not None else None,
            "rollback_form": (
                "downgrade to previous wheel + reinstall from sdist"
                if args.previous_wheel is not None else
                "uninstall + reinstall from sdist (no previous version "
                "published yet — first-release form)"
            ),
            "tested_at": datetime.now(timezone.utc).isoformat(),
            "steps": steps,
            "result": "fail" if failed else "pass",
        }
        problems = validate_receipt(receipt)
        if problems:
            raise RuntimeError("receipt invalid: " + "; ".join(problems))
        out_dir = (checkout / args.out_dir).resolve() \
            if not args.out_dir.is_absolute() else args.out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "rollback.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(f"release-rollback: {'FAIL' if failed else 'OK'} "
              f"({len(steps)} steps, {len(failed)} failed)")
        return 1 if failed else 0
    except RuntimeError as exc:
        print(f"release-rollback: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
