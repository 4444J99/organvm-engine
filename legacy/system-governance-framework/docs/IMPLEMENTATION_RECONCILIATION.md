# Implementation reconciliation guide

This public snapshot retains reusable evidence and verification principles from the source.
The operational workstream history, private repository coordinates, exact PR/run identifiers
and commit/tree receipts are omitted. The original dated records remain in the private source
identified by [PROVENANCE.md](../PROVENANCE.md).

`config/implementation-program.json` is now an explicitly synthetic coverage fixture: it keeps
the 25 gate definitions and dependency graph, uses example owners, and marks every gate
unresolved. It does not attest that any system was inspected, implemented or accepted.

## Evidence boundaries

| Claim | Evidence needed |
| --- | --- |
| Independent oversight | Authenticated authority and review boundaries; labels alone do not establish independence. |
| Bootstrap validation | A separately reviewed defining revision; a new workflow cannot prove its own admission. |
| Candidate execution | The actual checkout revision and job evidence; a PR-associated check alone may refer to a base or synthetic merge. |
| Test execution | Step-level observations; aggregate failure alone does not establish whether tests ran. |
| Publication | Evidence after upload or push; a generated receipt describes only what was observed when generated. |
| Trusted receipt context | Separately authenticated observations; a candidate's own flags and hashes do not authenticate them. |
| Enforced governance | Effective policy and required gates; passing optional CI does not establish enforcement. |
| Retirement of authority | An inventory and explicit retirement proof; adding narrow trust does not remove older authority. |
| Platform controls | Actual account/admin evidence; a valid inventory or vendor announcement does not establish effective settings. |
| Exposure classification | Current content/history review, stable identity and scoped authorization; names or visibility alone are insufficient. |

## Retained workflow interface

The reusable CI template's `coverage-enabled` input accepts `auto`, `'true'` or `'false'` as
strings. Explicit boolean callers must quote their values. Composite `validate=false` is
rejected because skipped validation cannot establish trustworthy configuration. The defining
workflow identity must be available; missing identity fails closed.

Reusable workflow examples keep token-presence detection separate from caller test commands.
These nested templates are reference material. They do not run as `organvm-engine` workflows
and do not establish a current deployment or security posture.

## Running the offline auditor

From the snapshot's development environment installed with `pip install -e '.[dev]'`:

```sh
python scripts/audit_execution_receipt.py supplied-receipt.json --context authenticated-observations.json
```

The context must come from a separately authenticated observation source, not fields in the
candidate receipt. This CLI does not establish that authentication. It reads the two supplied
files and prints structured findings without modifying either file or contacting a service.

Exit codes are 0 for verified supplied-evidence consistency, 1 for rejected evidence, and 2 for
unknown or unavailable trusted context. No exit code grants merge, deployment or publication
authority; output retains `production_authorized: false`.

## Scope of example validation

The bundled validators and tests exercise schema rules, required gate coverage, dependency
consistency, trusted workflow inputs and receipt failure modes. Their success is not evidence
of live branch protection, effective AI-provider policy, private/public access boundaries,
production deployment, historical merge acceptance or a completed estate census.
