"""Heartbeat daemon for the Cyclic Dispatch Protocol (SPEC-024 Phase 5).

A periodic polling daemon that:
1. Iterates all active relay cycles
2. Calls check_status() on each dispatch record via its backend
3. Transitions completed dispatches (DRAFT_RETURNED -> FORTIFY-ready)
4. Generates a JSON health report of active/completed/failed dispatches
5. Optionally sends webhook notifications on state changes

Designed to run as a macOS LaunchAgent on a 15-minute interval, or
invoked manually via ``organvm fabrica heartbeat``.
"""

from __future__ import annotations

import json
import logging
import os
import plistlib
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from organvm_engine.fabrica.backends import get_backend
from organvm_engine.fabrica.models import DispatchRecord, DispatchStatus, RelayPhase
from organvm_engine.fabrica.state import valid_transition
from organvm_engine.fabrica.store import (
    fabrica_dir,
    load_active_intents,
    load_dispatches,
    load_transitions,
    log_transition,
    save_dispatch,
)

logger = logging.getLogger("organvm.fabrica.heartbeat")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_dispatches(intent_id: str) -> list[DispatchRecord]:
    """Return the latest version of each dispatch for an intent.

    The fabrica store is append-only — updates are appended as new
    entries with the same ``id``. This function deduplicates by keeping
    the last entry per dispatch ID, which reflects the most recent state.
    """
    all_records = load_dispatches(intent_id=intent_id)
    by_id: dict[str, DispatchRecord] = {}
    for record in all_records:
        by_id[record.id] = record  # last write wins
    return list(by_id.values())


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLIST_LABEL = "com.organvm.fabrica.heartbeat"
DEFAULT_INTERVAL_SECONDS = 900  # 15 minutes
EXEC_TIMEOUT_SECONDS = 300
PLIST_FILENAME = f"{PLIST_LABEL}.plist"

# Statuses that indicate a dispatch is still in flight and should be polled
_POLLABLE_STATUSES = frozenset({
    DispatchStatus.DISPATCHED,
    DispatchStatus.IN_PROGRESS,
})

# Statuses that indicate a dispatch is done (no further polling)
_TERMINAL_STATUSES = frozenset({
    DispatchStatus.MERGED,
    DispatchStatus.REJECTED,
    DispatchStatus.FORTIFIED,
    DispatchStatus.TIMED_OUT,
})


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PollResult:
    """Result of polling a single dispatch record."""

    record_id: str
    backend: str
    old_status: DispatchStatus
    new_status: DispatchStatus
    changed: bool
    pr_url: str | None = None
    error: str | None = None


@dataclass
class HeartbeatReport:
    """Summary of a single heartbeat cycle."""

    timestamp: float = field(default_factory=time.time)
    active_intents: int = 0
    total_dispatches: int = 0
    polled: int = 0
    changed: int = 0
    completed: int = 0
    failed: int = 0
    errors: int = 0
    poll_results: list[dict[str, Any]] = field(default_factory=list)
    transitions: list[dict[str, str]] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "heartbeat_report",
            "timestamp": self.timestamp,
            "active_intents": self.active_intents,
            "total_dispatches": self.total_dispatches,
            "polled": self.polled,
            "changed": self.changed,
            "completed": self.completed,
            "failed": self.failed,
            "errors": self.errors,
            "poll_results": self.poll_results,
            "transitions": self.transitions,
            "duration_seconds": self.duration_seconds,
        }


# ---------------------------------------------------------------------------
# Core heartbeat logic
# ---------------------------------------------------------------------------

def poll_active_relays() -> list[PollResult]:
    """Iterate all active dispatch records and poll their backends for updates.

    Returns a list of PollResult objects, one per dispatch record that was
    checked. Only records in pollable states (DISPATCHED, IN_PROGRESS) are
    polled; terminal records are skipped.
    """
    results: list[PollResult] = []
    intents = load_active_intents()

    for intent in intents:
        dispatches = _latest_dispatches(intent.id)
        for record in dispatches:
            if record.status in _TERMINAL_STATUSES:
                continue
            if record.status not in _POLLABLE_STATUSES:
                # DRAFT_RETURNED is not terminal but also not pollable --
                # it awaits human FORTIFY action, not backend polling
                continue

            result = _poll_single_record(record)
            results.append(result)

    return results


def _poll_single_record(record: DispatchRecord) -> PollResult:
    """Poll a single dispatch record via its backend."""
    old_status = record.status
    try:
        backend = get_backend(record.backend)
        updated = backend.check_status(record)
        changed = updated.status != old_status
        if changed:
            save_dispatch(updated)
            logger.info(
                "Dispatch %s (%s): %s -> %s",
                record.id, record.backend,
                old_status.value, updated.status.value,
            )
        return PollResult(
            record_id=record.id,
            backend=record.backend,
            old_status=old_status,
            new_status=updated.status,
            changed=changed,
            pr_url=updated.pr_url,
        )
    except Exception as exc:
        logger.warning(
            "Failed to poll dispatch %s (%s): %s",
            record.id, record.backend, exc,
        )
        return PollResult(
            record_id=record.id,
            backend=record.backend,
            old_status=old_status,
            new_status=old_status,
            changed=False,
            error=str(exc),
        )


def transition_completed(poll_results: list[PollResult]) -> list[dict[str, str]]:
    """For dispatches that reached DRAFT_RETURNED, log that FORTIFY is ready.

    This does NOT auto-approve -- it transitions the relay cycle to
    the FORTIFY phase so a human can review. Returns a list of
    transition descriptions.
    """
    transitions: list[dict[str, str]] = []

    # Collect intent_ids for dispatches that just became DRAFT_RETURNED
    newly_returned_intent_ids: set[str] = set()
    for result in poll_results:
        if result.changed and result.new_status == DispatchStatus.DRAFT_RETURNED:
            # Look up the dispatch to find its intent_id
            intents = load_active_intents()
            for intent in intents:
                dispatches = _latest_dispatches(intent.id)
                for d in dispatches:
                    if d.id == result.record_id:
                        newly_returned_intent_ids.add(intent.id)
                        break

    # For each intent with newly returned dispatches, check if ALL
    # dispatches for that intent are now in a non-pollable state
    for intent in load_active_intents():
        if intent.id not in newly_returned_intent_ids:
            continue

        dispatches = _latest_dispatches(intent.id)
        all_done = all(d.status not in _POLLABLE_STATUSES for d in dispatches)
        if not all_done:
            continue

        # All dispatches for this intent are done -- the intent's
        # relay cycle should already be in FORTIFY (set during HANDOFF),
        # but log a note that it is ready for human review
        packet_transitions = load_transitions(packet_id=intent.packet_id)
        current_phase_str = packet_transitions[-1]["to"] if packet_transitions else "release"
        current_phase = RelayPhase(current_phase_str)

        if current_phase == RelayPhase.FORTIFY:
            transition_note = {
                "intent_id": intent.id,
                "packet_id": intent.packet_id,
                "event": "fortify_ready",
                "message": "All dispatches returned -- ready for human FORTIFY review",
            }
            transitions.append(transition_note)
            logger.info(
                "Intent %s (packet %s): all dispatches returned, ready for FORTIFY",
                intent.id, intent.packet_id,
            )
        elif current_phase == RelayPhase.HANDOFF and valid_transition(
            RelayPhase.HANDOFF, RelayPhase.FORTIFY,
        ):
            # Transition HANDOFF -> FORTIFY since dispatches are done
            log_transition(
                intent.packet_id,
                RelayPhase.HANDOFF,
                RelayPhase.FORTIFY,
                reason="heartbeat: all dispatches returned",
            )
            transition_note = {
                "intent_id": intent.id,
                "packet_id": intent.packet_id,
                "event": "handoff_to_fortify",
                "message": "Heartbeat advanced HANDOFF -> FORTIFY",
            }
            transitions.append(transition_note)
            logger.info(
                "Intent %s: heartbeat advanced HANDOFF -> FORTIFY",
                intent.id,
            )

    return transitions


def generate_health_report(
    poll_results: list[PollResult],
    transitions: list[dict[str, str]],
    start_time: float,
) -> HeartbeatReport:
    """Generate a summary health report from the heartbeat cycle."""
    intents = load_active_intents()
    all_dispatches: list[DispatchRecord] = []
    for intent in intents:
        all_dispatches.extend(_latest_dispatches(intent.id))

    completed = sum(
        1 for d in all_dispatches
        if d.status in (DispatchStatus.MERGED, DispatchStatus.FORTIFIED)
    )
    failed = sum(
        1 for d in all_dispatches
        if d.status in (DispatchStatus.REJECTED, DispatchStatus.TIMED_OUT)
    )
    errors = sum(1 for r in poll_results if r.error is not None)
    changed = sum(1 for r in poll_results if r.changed)

    return HeartbeatReport(
        active_intents=len(intents),
        total_dispatches=len(all_dispatches),
        polled=len(poll_results),
        changed=changed,
        completed=completed,
        failed=failed,
        errors=errors,
        poll_results=[
            {
                "record_id": r.record_id,
                "backend": r.backend,
                "old_status": r.old_status.value,
                "new_status": r.new_status.value,
                "changed": r.changed,
                "pr_url": r.pr_url,
                "error": r.error,
            }
            for r in poll_results
        ],
        transitions=transitions,
        duration_seconds=round(time.time() - start_time, 3),
    )


def _save_report(report: HeartbeatReport) -> Path:
    """Persist the heartbeat report to the fabrica logs directory."""
    logs_dir = fabrica_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    report_path = logs_dir / "heartbeat-latest.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n")

    # Also append to the heartbeat log (append-only)
    log_path = logs_dir / "heartbeat.jsonl"
    with log_path.open("a") as f:
        f.write(json.dumps(report.to_dict()) + "\n")

    return report_path


def _send_webhook(report: HeartbeatReport) -> None:
    """Send a webhook notification if ORGANVM_HEARTBEAT_WEBHOOK is set.

    Sends the report as a JSON POST body. Failures are logged but
    do not abort the heartbeat.
    """
    webhook_url = os.environ.get("ORGANVM_HEARTBEAT_WEBHOOK")
    if not webhook_url:
        return

    try:
        import urllib.request

        data = json.dumps(report.to_dict()).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info("Webhook sent: %d", resp.status)
    except Exception as exc:
        logger.warning("Webhook delivery failed: %s", exc)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_heartbeat(*, quiet: bool = False, json_output: bool = False) -> HeartbeatReport:
    """Execute one heartbeat cycle: poll, transition, report.

    This is the main function called by both the CLI subcommand
    and the LaunchAgent.

    Returns the HeartbeatReport for the cycle.
    """
    start_time = time.time()

    if not quiet:
        logger.info("Heartbeat cycle starting")

    # 1. Poll all active dispatches
    poll_results = poll_active_relays()

    # 2. Transition completed dispatches
    transitions = transition_completed(poll_results)

    # 3. Generate health report
    report = generate_health_report(poll_results, transitions, start_time)

    # 4. Persist report
    report_path = _save_report(report)

    # 5. Optional webhook notification (only if something changed)
    if report.changed > 0 or report.errors > 0:
        _send_webhook(report)

    if not quiet:
        if json_output:
            json.dump(report.to_dict(), sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            _print_summary(report, report_path)

    return report


def _print_summary(report: HeartbeatReport, report_path: Path) -> None:
    """Print a human-readable summary of the heartbeat cycle."""
    print(f"Heartbeat complete ({report.duration_seconds:.1f}s)")
    print(f"  Active intents:    {report.active_intents}")
    print(f"  Total dispatches:  {report.total_dispatches}")
    print(f"  Polled:            {report.polled}")
    print(f"  Changed:           {report.changed}")
    print(f"  Completed:         {report.completed}")
    print(f"  Failed:            {report.failed}")
    if report.errors:
        print(f"  Errors:            {report.errors}")

    if report.poll_results:
        print()
        for r in report.poll_results:
            marker = "*" if r["changed"] else " "
            err = f"  ERR: {r['error']}" if r.get("error") else ""
            print(
                f"  {marker} {r['record_id'][:8]}  [{r['backend']:10s}]"
                f"  {r['old_status']:15s} -> {r['new_status']:15s}{err}",
            )

    if report.transitions:
        print()
        for t in report.transitions:
            print(f"  >> {t['event']}: {t['message']}")

    print(f"\n  Report: {report_path}")


# ---------------------------------------------------------------------------
# LaunchAgent plist management
# ---------------------------------------------------------------------------

def _plist_dir() -> Path:
    """Return ~/Library/LaunchAgents/."""
    return Path.home() / "Library" / "LaunchAgents"


def _plist_path() -> Path:
    """Return the full path to the heartbeat plist."""
    return _plist_dir() / PLIST_FILENAME


def _python_executable() -> str:
    """Return the path to the current Python interpreter."""
    return sys.executable


def generate_plist(*, interval: int = DEFAULT_INTERVAL_SECONDS) -> dict[str, Any]:
    """Generate the LaunchAgent plist dictionary.

    Uses the current Python interpreter path so the plist runs
    in the same environment where organvm-engine is installed.
    """
    home = str(Path.home())
    logs_dir = str(fabrica_dir() / "logs")

    return {
        "Label": PLIST_LABEL,
        "ProgramArguments": [
            _python_executable(),
            "-m", "organvm_engine.fabrica.heartbeat",
        ],
        "StartInterval": interval,
        "RunAtLoad": False,
        "ProcessType": "Background",
        "Nice": 10,
        "LowPriorityIO": True,
        "ExecTimeout": EXEC_TIMEOUT_SECONDS,
        "StandardOutPath": f"{logs_dir}/heartbeat-stdout.log",
        "StandardErrorPath": f"{logs_dir}/heartbeat-stderr.log",
        "EnvironmentVariables": {
            "PATH": f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{home}/.local/bin",
            "HOME": home,
        },
    }


def install_launchagent(*, interval: int = DEFAULT_INTERVAL_SECONDS) -> Path:
    """Generate the plist and load the LaunchAgent.

    Returns the path to the installed plist.
    """
    plist_data = generate_plist(interval=interval)
    plist_path = _plist_path()

    # Ensure directories exist
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    logs_dir = fabrica_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Unload existing agent if present
    _unload_agent_if_loaded()

    # Write plist
    with plist_path.open("wb") as f:
        plistlib.dump(plist_data, f)

    # Load the agent
    subprocess.run(
        ["launchctl", "load", str(plist_path)],
        check=True,
        capture_output=True,
    )

    print(f"Installed LaunchAgent: {plist_path}")
    print(f"  Label:    {PLIST_LABEL}")
    print(f"  Interval: {interval}s ({interval // 60}m)")
    print(f"  Python:   {_python_executable()}")
    print(f"  Logs:     {logs_dir}/")

    return plist_path


def uninstall_launchagent() -> None:
    """Unload and remove the LaunchAgent plist."""
    _unload_agent_if_loaded()
    plist_path = _plist_path()
    if plist_path.exists():
        plist_path.unlink()
        print(f"Removed LaunchAgent: {plist_path}")
    else:
        print(f"No plist found at {plist_path}")


def _unload_agent_if_loaded() -> None:
    """Unload the LaunchAgent if it is currently loaded."""
    plist_path = _plist_path()
    if not plist_path.exists():
        return
    subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        capture_output=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# __main__ entry point (for LaunchAgent invocation)
# ---------------------------------------------------------------------------

def main() -> int:
    """CLI entry point for ``python -m organvm_engine.fabrica.heartbeat``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        report = run_heartbeat(quiet=False, json_output=False)
        return 0 if report.errors == 0 else 1
    except Exception:
        logger.exception("Heartbeat daemon failed")
        return 2


if __name__ == "__main__":
    sys.exit(main())
