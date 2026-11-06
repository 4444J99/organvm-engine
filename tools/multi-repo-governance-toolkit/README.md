# multi-repo-governance-toolkit

[![CI](https://github.com/4444J99/organvm-engine/actions/workflows/governance-toolkit-ci.yml/badge.svg?branch=main)](https://github.com/4444J99/organvm-engine/actions/workflows/governance-toolkit-ci.yml)

When one owner runs dozens of separate GitHub repos, the registry, community-health files and metadata drift apart, and personal details leak into public code. This toolkit keeps them consistent with scripts that validate the registry, generate GitHub config, report PR status and lint every file for names, emails and home paths.

## Quick start

`examples/sample-registry.json` is a three-repo registry with one deliberate error: `web` depends on `auth`, which isn't in the registry. The dependency validator catches it and exits 1:

```console
$ REGISTRY_PATH=examples/sample-registry.json V4_REPORT=/tmp/v4-report.json python scripts/v4-dependency-validation.py
================================================================================
V4: DEPENDENCY GRAPH VALIDATION
================================================================================

  Total repos: 3
  Total dependency edges: 3

── Check 1: Dependency targets exist ──
  FAIL: 1 dependencies point to non-existent repos:
    example-org/web -> example-org/auth (NOT IN REGISTRY)

── Check 2: No self-dependencies ──
  PASS: No self-dependencies

── Check 3: No back-edges (I->II->III direction) ──
  PASS: No back-edges in I->II->III chain

── Check 4: No circular dependencies ──
  PASS: No circular dependencies

── Check 5: Cross-organ dependency summary ──

================================================================================
V4 SUMMARY
================================================================================
  Total dependency edges: 3
  Missing targets: 1
  Self-dependencies: 0
  Back-edges: 0
  Circular dependencies: 0
  Total violations: 1

  V4 RESULT: ISSUES FOUND

  Report written to /tmp/v4-report.json
$ echo $?
1
```

## What's inside

- `scripts/` — Python utilities for validating, normalizing and reporting on repository registry data, generating per-repo seed files and org-level GitHub configs, and checking publication authorizations.
- `templates/` — reusable ADR, changelog, badge and dependency-manifest templates.
- `.github-template/` — community-health file templates (code of conduct, contributing, security, issue and PR templates) and an org profile template, using `{{PLACEHOLDER}}` values.
- `tests/` — pytest suite.

Scripts that scan a local workspace read its root from the `ORGANVM_WORKSPACE` environment variable (default: current directory).

GitHub configuration generation accepts the owning configuration with `--config`.
It generates per-organ configs and profile READMEs. The shared meta profile needs
the corpus renderer and its registry, metrics, and snapshot inputs; it is not
generated or overwritten by this toolkit.

The DONE-ID validator reads `data/done-id-counter.json` and
`INST-INDEX-RERUM-FACIENDARUM.md` from the current directory, or from the corpus
checkout selected with `--repo-root /path/to/corpus`. Add `--staged` to validate
that checkout's staged IRF additions against the staged counter and the complete
staged assignment set.

The polish utility consumes the owning CI template through `--ci-template`:

```bash
python scripts/platinum-polish-vi-vii.py --ci-template /path/to/ci-minimal.yml
```

This previews the configured targets. Add `--write` to apply the changes after
checking the template and target list.

## Running the tests

```bash
python -m pip install pytest pyyaml
python -m pytest
```

The host repository runs this suite through its root
`.github/workflows/governance-toolkit-ci.yml` workflow.

## License

MIT — see [LICENSE](LICENSE).

## Identity lint

`scripts/identity-lint.py` flags emails, home paths and denylisted names. Denylisted
terms are stored only as salted SHA-256 hashes in repository secrets
(`IDENTITY_SALT`, `IDENTITY_DENYLIST`, optional `IDENTITY_OWN_NAMES`); nothing
guessable is committed. Without those secrets (forks, local runs) the hash check is
skipped with a notice and the plain-pattern checks still run. In CI it is warning-only.
