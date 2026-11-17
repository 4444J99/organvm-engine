# Documentation estate audits

This directory contains reproducible, privacy-bounded analyses of repository
documentation. The public artifacts may include aggregate counts and rows for
public repositories. They must not publish private repository names, paths,
descriptions, findings, or evidence.

## Reader-mode estate audit

Run the builder with the directory containing the seven live inventory exports:

```bash
python -m pip install -e '.[audit]'
ORGANVM_DOC_AUDIT_INPUT_DIR=/path/to/private/audit-exports \
  python docs/audits/build_reader_mode_estate_audit.py
```

In a restricted environment that does not allow Jupyter kernel sockets, use the
documented in-process execution fallback:

```bash
ORGANVM_DOC_AUDIT_INPUT_DIR=/path/to/private/audit-exports \
ORGANVM_NOTEBOOK_EXECUTION=in-process \
  python docs/audits/build_reader_mode_estate_audit.py
```

The builder executes
[`2026-08-31-reader-mode-estate-audit.ipynb`](2026-08-31-reader-mode-estate-audit.ipynb)
top to bottom and regenerates:

- `reader-mode-input-manifest.json` — source filenames, row and visibility
  counts, and SHA-256 hashes without row-level repository data;
- `reader-mode-estate-summary.json` — aggregate public/private coverage,
  class counts, and mean scores;
- `reader-mode-public-rollout.json` — public inventory plus the five pilots and
  next twenty conversions;
- `reader-mode-estate-audit.md` — the readable decision record.

The raw exports are transient, access-controlled inputs and are intentionally
not committed. This directory is therefore not a self-contained copy of the
underlying audit data. A rerun requires separately retained, authorized copies
matching the hashes in `reader-mode-input-manifest.json`.

The notebook fails before publishing when repository keys are duplicated, the
expected 323-row scope or 239 public / 84 private split is incomplete, class or
visibility vocabulary drifts, a source omits a rubric dimension, a score leaves
the 0–4 range, or a source total disagrees with the recomputed seven-dimension
total. Before serialization, private references in public prose are redacted. A
final privacy gate scans every public artifact in this directory for complete
private `owner/repository` identifiers, backticked private slugs, and
private-only bare slugs. Known public prose that collides lexically with a
private slug is rewritten to an equivalent non-colliding phrase before the
fail-closed scan; the scanner itself retains full private-slug coverage.
For the Python builder, only the literal values inside the named source and
rewrite-control declarations are excluded. Identical strings anywhere else in
the program remain privacy-bearing and fail the scan.

## Authority boundary

The notebook analyzes and schedules work. It does not define the documentation
contract. Editorial rules live in `organvm/editorial-standards`; schemas live in
`organvm-iv-taxis/schema-definitions`; validation and scoring code live in this
repository; fleet adoption policy lives in `organvm/.github`; conversion waves,
execution tracking, and receipts belong to
`organvm-iv-taxis/orchestration-start-here`.
