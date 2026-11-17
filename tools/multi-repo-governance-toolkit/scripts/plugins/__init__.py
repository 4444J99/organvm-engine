"""organvm meta-plugins — 3 priority orchestrators per IRF-SYS-184.

Each plugin is invoked via `organ-cli.py plugin <name> [args...]`.
The companion SKILL.md files in `.claude/skills/<name>/` describe the
human-facing prompt surface; this package holds the executable backings.

Plugins:
    session_orchestrator     — master sequencer for Phase 0→3 chain
    vacuum_radar             — real-time N/A detection across IRF and repo state
    atom_logger              — append a structured work-atom to the prompt registry
"""

__all__ = [
    "session_orchestrator",
    "vacuum_radar",
    "atom_logger",
]
