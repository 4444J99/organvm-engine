# Public interface and version policy (draft for review)

Scope: issue #194. This document records the contract that is *tested today*; it does not
choose a 1.0 label, tag or publish anything. `pyproject.toml` declares `0.1.0`; no release
baseline has been published, so every incompatibility below is judged against the committed
baselines, not against a past release.

## Interfaces and their status

| Interface | Promise | Machine-checked by |
|-----------|---------|--------------------|
| `organvm` CLI command tree: command names, argument names and flags, whether an argument is required, whether it takes a value, enumerated `choices` | Stable for consumers; changes are classified below | `docs/api/cli-surface.json` + `tests/test_api_surface.py`; `python -m organvm_engine.api_surface check` |
| Package version | `pyproject.toml` `version` equals `organvm_engine.__version__` | `tests/test_api_surface.py` |
| Python imports under `organvm_engine.*` | Not yet a promise (no public/private split declared) | not checked; to be decided under #194 |
| JSON/evidence schemas, exit codes | Not yet inventoried here | not checked; separate versioning to be decided under #194 |

## Classification of a CLI change

- Breaking: command removed; argument or flag removed; argument became required or a new
  required argument appeared; value arity changed; an accepted choice removed; choices
  newly restricted.
- Compatible: command added; optional argument or flag added; choice added; choices
  unrestricted.

## Workflow

1. Change the CLI.
2. `python -m organvm_engine.api_surface check` reports `BREAKING` / `compatible` lines.
3. Additive change: tests stay green with a stale baseline (so concurrent PRs do not conflict
   on the JSON); refresh it with `python -m organvm_engine.api_surface write` when the new
   surface should become part of the promise.
4. Breaking change: while the package is pre-release (`0.x`) it is allowed only when
   deliberate. Run `write`, add a `CHANGELOG.md` entry under `Unreleased` that names the
   removed or changed command, and say so in the PR. The baseline refresh makes the break
   reviewable in the diff; the test suite rejects a breaking change that leaves the baseline
   stale.

## Open decisions (not made here)

- Which Python imports are public.
- Separate version policy for portable evidence schemas, deprecation windows and migration
  formats.
- Whether a release freeze branch is needed, and the first published baseline. Publishing a
  tag or package remains a separate approval and provenance gate.
