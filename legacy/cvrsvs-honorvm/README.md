# Cvrsvs Honorvm

**Retired proposal for a governance library for multi-repository open-source ecosystems.**

This directory preserves a scrubbed source snapshot for reference. See
[PROVENANCE.md](PROVENANCE.md) for its source commit and import history.

Promotion state machines, dependency DAG validation, and seed contract parsing
were planned for extraction from [organvm-engine](https://github.com/4444J99/organvm-engine)
into a standalone, pip-installable library. This snapshot contains documentation
and configuration; it has no Python package, build metadata, or workflow files.

Named after the Roman *cursus honorum* — the sequential order of public offices in the Republic. ORGANVM orthography: V for U.

## Historical Status

The status and plans below are retained from the source README as historical context.

**INCUBATOR** — extraction in progress. Not yet published to PyPI.

NLnet NGI0 Commons Fund application pending (April 1, 2026).

## Historical Proposed Scope

1. **Promotion State Machine** — configurable finite state machine governing repository lifecycle transitions with infrastructure audit gates and event emission
2. **Dependency Graph Validator** — DAG validator enforcing dependency flow rules across organizational boundaries with cycle detection and back-edge enforcement
3. **Seed Contract System** — declarative YAML contract format (`seed.yaml`) for declaring repository metadata, dependency edges, and event subscriptions

## License

The preserved source [LICENSE](LICENSE) declares Creative Commons
Attribution-ShareAlike 4.0 International (SPDX: CC-BY-SA-4.0).
