# docs/history — superseded artifacts, kept for the record

## patch2-superseded.diff

An unapplied diff that lived at the repo root. **Both of its hunks already
landed on main; the file is a historical artifact, not a pending fix.**

- Hunk 1 removed a duplicate `--format` argument from the `registry ls`
  subparser (`choices=["text", "json"]`, default `"text"`). The `ls` parser
  in `src/organvm_engine/cli/__init__.py` now carries a single `--format`
  (choices `table`/`json`, default `table`) — argparse would reject a
  duplicate option string, so the removal is confirmed in place.
- Hunk 2 added `DEFINES`, `REFERENCES`, `IMPLEMENTS`, `GROUNDS` and
  `EXTRACTED_FROM` to the `RelationType` expected set in
  `tests/test_ontology_relations.py`. All five values are in
  `src/organvm_engine/ontology/relations.py:38-42`.

Relocated from the root by `git mv` for issue #196 (2026-11-23) so a new
contributor does not mistake it for an unlanded fix. Do not re-apply it:
the hunks no longer apply cleanly, and applying them would duplicate the
landed values.
