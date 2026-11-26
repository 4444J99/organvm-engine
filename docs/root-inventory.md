# Root inventory — every root entry, classified

Verified against live main `02db5d25` (2026-11-23) for issue #196
([experience] Can a new contributor or user navigate, install and verify
Engine without unexplained root sprawl?). 34 entries. This is the inventory
the plan's step 1 requires; the relocation map below it is step 3, executed
in the same change only where the evidence is conclusive.

## Classification

| Entry | Type | Consumer | Required at root? | Status |
|---|---|---|---|---|
| `.claude/` | dir (tool config) | Claude Code | Yes (tool reads it) | Live |
| `.codex/` | dir (tool config) | Codex | Yes (tool reads it) | Live |
| `.conductor/` | dir (tool config) | Conductor | Yes (tool reads it) | Live |
| `.editorconfig` | file | Editors | Yes (convention) | Live |
| `.gitattributes` | file | Git | Yes | Live |
| `.github/` | dir | GitHub Actions | Yes | Live |
| `.gitignore` | file | Git | Yes | Live |
| `.opencode/` | dir (plans) | Opencode agent plans | Yes (tool reads it) | Live |
| `.sops/` | dir (docs) | SOP docs | Yes (docs) | Live |
| `AGENTS.md` | file (generated) | Agents + `context sync` | Yes — generated block, do not hand-edit | Generated |
| `CHANGELOG.md` | file | Contributors, release-drafter | Yes | Live, current |
| `CLAUDE.md` | file (hand doctrine + generated block) | Claude Code + `context sync` | Yes | Live; hand part fixed in #196 |
| `CONTRIBUTING.md` | file | Contributors | Yes | Live; install path fixed in #196 |
| `GEMINI.md` | file (generated) | Gemini + `context sync` | Yes — generated block, do not hand-edit | Generated |
| `LICENSE` | file | Legal / packaging | Yes | Live |
| `README.md` | file | Everyone | Yes | Live; install + CLI examples fixed in #196 |
| `SECURITY.md` | file | Reporters | Yes | Live; advisory link fixed in #196 |
| `docs/` | dir | Docs, audits, research | Yes | Live |
| `done.sh` | file (executable) | `tests/test_portal_done.py` runs it | **Yes — LIVE, do not move** | Live |
| `ecosystem/` | dir (data) | `ecosystem/` module | Yes (data) | Live |
| `ecosystem.yaml` | file (data) | `ecosystem/` module | Yes (data) | Live; counts fixed in #196 |
| `legacy/` | dir (history) | None (no code/test references) | No | Historical — deferred, see below |
| `network-map.yaml` | file (data) | `network/` module | Yes (data) | Live; `last_scanned` 2026-03-20, stale-dated |
| `notebooks/` | dir | None (no code/test references) | No | Historical — deferred, see below |
| `organvm-engine` | gitlink | None (no `.gitmodules`, empty dir) | No | **Dead — removed in #196** |
| `patch2.diff` | file | None (no references) | No | **Superseded — relocated in #196** |
| `pyproject.toml` | file | Packaging, ruff, pyright, pytest | Yes | Live |
| `receipts/` | dir | `receipt:engine:` URI resolution | **Yes — LIVE, do not move** | Live |
| `scripts/` | dir | `consolidate-workspace.py` | Yes | Live |
| `seed.yaml` | file (data) | `seed/` module | Yes (data) | Live |
| `signatures/` | dir | CLAssistant reads `signatures/cla.json` from main | **Yes — LIVE, do not move** | Live |
| `src/` | dir | Package | Yes | Live |
| `tests/` | dir | pytest | Yes | Live |
| `tools/` | dir | Multi-repo governance toolkit | Yes | Live |

## Evidence for the verdicts that move things

- **`done.sh` is live, not a leftover.** `tests/test_portal_done.py:33`
  runs `bash done.sh` (BIFRONS Epic 6 acceptance predicate: one star's
  exchange through the whole portal loop). Moving it would break the test.
  The plan's step 2 check is what saved it: verify before touching.
- **`patch2.diff` is superseded, both halves landed.** The RelationType
  values it adds (`DEFINES`, `REFERENCES`, `IMPLEMENTS`, `GROUNDS`,
  `EXTRACTED_FROM`) are all in `src/organvm_engine/ontology/relations.py:38-42`;
  the `--format` duplicate it removes is gone from `cli/__init__.py` (the
  `ls` subparser now carries a single `--format`, choices `table`/`json` —
  argparse would reject a duplicate). Relocated to
  `docs/history/patch2-superseded.diff` with a note; history preserved by
  `git mv`.
- **`organvm-engine` gitlink is dead.** No `.gitmodules` mapping; the working
  directory is empty; the pinned commit `60aa4a86` is not an ancestor of main
  (it survives only on loop branch `limen/limen-050-4874`); no code or test
  references the path. Removed with `git rm --cached`.
- **`receipts/` and `signatures/` are live custody, not clutter.**
  `receipts/README.md` pins the `receipt:engine:<key>` resolution and a
  digest-bound ratification; `signatures/cla.json` is the CLA signatures file
  the CLAssistant action reads from main (see OE #240/#241/#245). Neither
  moves.
- **Agent entrypoints are not three duplicated doctrines** (the plan's step 4
  premise, corrected on re-verification). `AGENTS.md` (2,087 bytes) and the
  `ORGANVM:AUTO` block in `GEMINI.md` are auto-generated context managed by
  `organvm context sync` — hand edits inside the markers would be
  overwritten. Only `CLAUDE.md` lines 1–110 are hand doctrine, and the
  #196 fix touches only those (repo-local `.venv`, CI lint command).
  The 31 broken `../docs/logos/*.md` links `organvm docs audit` reports sit
  inside that generated block; they are a context-sync follow-up, not a
  hand edit.
- **`seed.yaml`'s `org: meta-organvm` is not drift.** It matches the code's
  workspace model (`paths.py`: `ORGANVM_WORKSPACE_DIR` layout,
  `<workspace>/meta-organvm/...`). The GitHub org moved to `4444J99`; the
  workspace directory did not. Do not "fix" it to `4444J99` without changing
  the seed-reader contract. The GitHub-side links (README authority,
  SECURITY.md advisories, CONTRIBUTING's orchestration link) were fixed to
  `4444J99/...` in #196 — those are the ones that were stale.

## Relocation map (deferred items)

- **`legacy/`** (cvrsvs-honorvm, petasum-super-petasum subprojects) and
  **`notebooks/`** (`prompt-audit.ipynb`): no code or test references either,
  but both are large historical content whose keep/port decision needs the
  owner's review. Recorded here, not moved: the issue forbids moving files
  merely for visual cleanliness, and a wrong move here destroys history a
  new contributor cannot reconstruct.
- **`network-map.yaml`**: `last_scanned` 2026-03-20 — the data is stale-dated
  but the file is live input to the `network/` module; refreshing it is a
  data refresh, not a relocation.
- **`ecosystem.yaml`**: counts were stale (`21 domain modules, 590+ tests`,
  `23 command groups`) and were corrected in #196 to the live values
  (`47 domain modules, ~6,800 tests`, `49 command groups`, counted from
  `src/organvm_engine/` and the argparse tree at `02db5d25`).

## Clean-room evidence (2026-11-23, main `02db5d25`)

Fresh clone, no private workspace, no corpus checkout, venv +
`pip install -e ".[dev]"`. Before the #196 fix:

- `pip install -r requirements.txt` (CONTRIBUTING's install path): fails,
  no such file.
- `organvm registry show recursive-engine--generative-entity` (README's
  example): traceback, `FileNotFoundError` for the default registry path
  `/home/hatch/Code/organvm/organvm-corpvs-testamentvm/repo-registry.json`;
  the named repo is not in the minimal fixture either.
- `organvm registry list`, `metrics calculate`, `context sync --dry-run`
  (bare README forms): same traceback.
- `organvm governance audit`: `FileNotFoundError: Rules file not found`
  (corpus governance rules) even with `--registry` — it needs
  `ORGANVM_CORPUS_DIR` too.
- `organvm seed validate` (bare): `0 passed, 0 failed` — silently vacuous
  without an `ORGANVM_WORKSPACE_DIR` layout.
- `organvm dispatch validate payload.json`: `payload.json` does not exist.
- `organvm context surfaces --workspace ~/Workspace --json`: `--workspace`
  is not an argument of that subcommand.
- `organvm docs validate project-record.yml --schema path/to/...`: no
  `project-record.yml` exists in the repo; the schema path was a placeholder.

After the #196 fix (same clean-room method, see
[docs/quickstart.md](quickstart.md)): the quickstart's representative
workflow runs end to end — registry validate/show/list and governance
check-deps against the fixture, seed validate PASS on a one-repo workspace,
dispatch validate PASS on the new fixture, metrics calculate against a
`/tmp` registry copy, `docs audit` reporting the two known findings.
The `load_registry` diagnostic now names the missing path and the
`--registry` / `ORGANVM_CORPUS_DIR` escape hatches instead of a bare
traceback (see `tests/test_registry.py`).
