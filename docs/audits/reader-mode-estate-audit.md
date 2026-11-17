# ORGANVM reader-mode documentation estate audit

Audit date: 2026-08-31

## Outcome

All **323** repositories visible through the linked GitHub context were classified and scored: **239 public** and **84 private**. The implementation uses existing editorial, schema, runtime, governance, and orchestration authorities rather than adding a documentation-engine repository.

The public contract is one canonical factual project record, evidence-linked material claims, class-specific reader routes, and truth repair before search expansion. Private repository identifiers and row-level findings remain outside this report.

## Data and validation

The audit uses seven authorized exports at one repository per row. All 323 source totals reconcile with the seven 0–4 dimension scores; repository identifiers are unique; and class, visibility, and expected coverage checks pass.

The public input manifest records source filenames, row and visibility counts, and SHA-256 hashes. Raw exports are not committed, so rerunning is possible only with separately retained authorized copies.

## Documentation classes

| Class | Public | Private |
|---|---:|---:|
| A | 36 | 9 |
| B | 41 | 14 |
| C | 45 | 16 |
| D | 12 | 0 |
| E | 22 | 6 |
| F | 83 | 39 |

## Authority map

| Responsibility | Canonical repository |
|---|---|
| Editorial contract, rubric, and templates | `organvm/editorial-standards` |
| Project and assertion schemas | `organvm-iv-taxis/schema-definitions` |
| Audit and validation runtime | `organvm/organvm-engine` |
| Fleet adoption policy | `organvm/.github` |
| Reusable CI invocation | `organvm-iv-taxis/system-governance-framework` |
| Rollout waves and execution receipts | `organvm-iv-taxis/orchestration-start-here` |

## Five pilots

Ranks combine public leverage, rhetorical coverage, source recommendations, and truth gates. The audit score is shown for traceability, not used as a standalone ordering function.

| Rank | Repository | Class | Score / 28 | Source priority | Why this pilot |
|---:|---|:---:|---:|---|---|
| 1 | `4444J99/limen` | A | 21 | pilot | claims-ledger and infrastructure/governance pilot |
| 2 | `organvm/the-thing-without-a-name` | A | 23 | P1 | creative, scholarly, production, and provenance pilot |
| 3 | `4444J99/peer-audited--behavioral-blockchain` | A | 22 | pilot | technical, commercial, ethical, and live-status pilot |
| 4 | `4444J99/your-fit-tailored` | A | 24 | pilot | specification-first theory/product pilot |
| 5 | `4444J99/hokage-chess` | B | 19 | pilot-after-truth-repair | prototype-vs-product pilot after mandatory truth repair |

## Next twenty conversions

| Rank | Repository | Class | Score / 28 | Source priority | Value / gap / leverage |
|---:|---|:---:|---:|---|---|
| 1 | `organvm-iii-ergon/public-record-data-scrapper` | A | 25 | ergon_wave_1 | strong public product/evidence front door |
| 2 | `organvm-iii-ergon/life-my--midst--in` | A | 26 | ergon_wave_1 | employment, identity theory, architecture, and evaluation |
| 3 | `organvm-iii-ergon/the-actual-news` | A | 26 | ergon_wave_1 | public purpose plus protocol/conformance evidence |
| 4 | `organvm-iii-ergon/classroom-rpg-aetheria` | A | 25 | ergon_wave_1 | pedagogy, product, system, and evaluator routes |
| 5 | `organvm-iii-ergon/parlor-games--ephemera-engine` | E | 21 | ergon_wave_1 | runnable creative system with honest design status |
| 6 | `organvm-ii-poiesis/ivi374ivi027-05` | B | 15 | unranked | bounded multimedia/literary work and preservation record |
| 7 | `organvm/a-organvm` | A | 18 | P0 | canonical flagship with no audience routing |
| 8 | `organvm/organvm-engine` | A | 11 | P0 | largest implementation-to-documentation mismatch |
| 9 | `organvm/radix-recursiva-solve-coagula-redi` | A | 22 | P1 | flagship theory/runtime synthesis |
| 10 | `organvm/recursive-engine--generative-entity` | A | 23 | P1 | mature theory/runtime flagship |
| 11 | `organvm/linguistic-atomization-framework` | A | 25 | P1 | balanced technical-humanities record |
| 12 | `organvm/alchemical-synthesizer` | A | 22 | P1 | creative technology flagship |
| 13 | `organvm/metasystem-master` | A | 24 | P0 | repair zero-byte and evidence drift before conversion |
| 14 | `organvm/adaptive-personal-syllabus` | A | 25 | P0 | repair tracked artifacts and provenance before conversion |
| 15 | `organvm-iv-taxis/system-governance-framework` | A | 23 | P0 | document the reusable enforcement surface |
| 16 | `organvm-iv-taxis/distribution-strategy` | B | 23 | P0 | source audience and search-intent mappings |
| 17 | `organvm-vii-kerygma/portfolio` | A | 26 | P0 | general, hiring, and client renderer |
| 18 | `organvm-vii-kerygma/showcase-portfolio` | A | 24 | P0 | humanities, curatorial, and grant renderer |
| 19 | `organvm-vii-kerygma/stakeholder-portal` | B | 19 | P0 | evaluator and operational evidence renderer |
| 20 | `organvm/4444J99` | D | 21 | P0 | problem-domain top-of-funnel above the internal ontology |

## Gates before expansion

- Correct false or stale implementation, deployment, test, owner, license, and provenance claims.
- Do not create audience editions for archives, forks, or deployment artifacts beyond their class minimum.
- Treat industry mappings as proposed unless a claim record substantiates pilot or deployment status.
- Keep private repository identifiers and evidence out of public generated inventories.
- Preserve the endpoint coverage caveat recorded in the aggregate summary.

## Reproduction boundary

Run `build_reader_mode_estate_audit.py` with `ORGANVM_DOC_AUDIT_INPUT_DIR` pointing to separately retained, authorized copies of the seven exports whose hashes appear in `reader-mode-input-manifest.json`. The public repository alone is not a self-contained copy of the raw audit data.
