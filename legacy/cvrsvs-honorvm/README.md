# Cvrsvs Honorvm

**Governance engine for multi-repository open-source ecosystems.**

Promotion state machines, dependency DAG validation, and seed contract parsing — extracted from [organvm-engine](https://github.com/meta-organvm/organvm-engine) as a standalone, pip-installable library.

Named after the Roman *cursus honorum* — the sequential order of public offices in the Republic. ORGANVM orthography: V for U.

## Status

**INCUBATOR** — extraction in progress. Not yet published to PyPI.

NLnet NGI0 Commons Fund application pending (April 1, 2026).

## What This Will Provide

1. **Promotion State Machine** — configurable finite state machine governing repository lifecycle transitions with infrastructure audit gates and event emission
2. **Dependency Graph Validator** — DAG validator enforcing dependency flow rules across organizational boundaries with cycle detection and back-edge enforcement
3. **Seed Contract System** — declarative YAML contract format (`seed.yaml`) for declaring repository metadata, dependency edges, and event subscriptions

## License

Apache License 2.0 (SPDX: Apache-2.0)
