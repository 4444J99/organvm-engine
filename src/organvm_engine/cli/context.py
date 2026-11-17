"""Context CLI commands."""

import argparse
import json
import sys


def cmd_context_surfaces(args: argparse.Namespace) -> int:
    from organvm_engine.contextmd.surfaces import (
        collect_conversation_corpus_surfaces,
        render_conversation_corpus_surfaces,
    )

    report = collect_conversation_corpus_surfaces(
        workspace=args.workspace,
        repo=getattr(args, "repo", None),
    )
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
    else:
        print(render_conversation_corpus_surfaces(report))
    return 1 if report["invalid_count"] > 0 else 0


def cmd_context_sync(args: argparse.Namespace) -> int:
    from organvm_engine.contextmd.sync import sync_all

    # --write overrides the default dry_run=True
    dry_run = not getattr(args, "write", False)
    if dry_run and getattr(args, "receipt", None) is not None:
        print("Error: --receipt requires --write", file=sys.stderr)
        return 1

    organs = [args.organ] if args.organ else None
    result = sync_all(
        workspace=args.workspace,
        registry_path=args.registry,
        dry_run=dry_run,
        organs=organs,
        receipt_path=getattr(args, "receipt", None),
        create_instruction_files=bool(getattr(args, "create_instruction_files", False)),
    )

    print("System Context Sync Results")
    print("─" * 40)
    print(f"  Updated: {len(result['updated'])}")
    print(f"  Created: {len(result['created'])}")
    print(f"  Skipped: {len(result['skipped'])}")
    declined = result.get("declined") or []
    if declined:
        print(f"  Declined (instruction file absent or without markers): {len(declined)}")
    if result["errors"]:
        print(f"  Errors:  {len(result['errors'])}")
        for e in result["errors"]:
            print(f"    - {e['path']}: {e['error']}")

    changes = result.get("changelog") or result.get("changes") or []
    if changes:
        print("\nChangelog")
        print("─" * 40)
        for change in changes:
            marker = _change_marker(change.get("action", "updated"))
            print(
                f"  {marker} {change['path']} "
                f"(+{change.get('added_lines', 0)}/-{change.get('removed_lines', 0)})",
            )

    if getattr(args, "diff", False) and changes:
        print("\nDiff")
        print("─" * 40)
        for change in changes:
            diff = change.get("diff")
            if diff:
                print(diff)

    if result.get("dry_run"):
        print("\n[DRY RUN] No files were modified.")
    elif result.get("receipt_path"):
        print(f"\nReceipt: {result['receipt_path']} ({result['receipt_sha256']})")

    return 1 if result["errors"] else 0


def cmd_context_migrate_legacy(args: argparse.Namespace) -> int:
    """Move legacy full AUTO blocks into docs/organvm-context.md, leaving the pointer."""
    from collections import defaultdict

    from organvm_engine.contextmd.migrate import migrate_legacy

    write = bool(getattr(args, "write", False))
    report = migrate_legacy(list(args.paths), write=write)

    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
        return 1 if report.by_action("error") else 0

    mode = "WRITE" if write else "DRY RUN"
    print(f"Legacy context migration [{mode}]")
    print("─" * 40)
    markers = {"migrate": "M" if write else "would M"}
    for item in report.files:
        if item.action == "migrate":
            extras = []
            if item.document:
                extras.append(f"docs {item.document}")
            if item.differing:
                extras.append("differing from the document source")
            suffix = f"  [{'; '.join(extras)}]" if extras else ""
            print(
                f"  {markers[item.action]} {item.path}  "
                f"words {item.words_before} -> {item.words_after}{suffix}",
            )
        elif item.action == "error":
            extras = []
            if item.document:
                extras.append(f"docs {item.document}")
            extras.append(item.reason)
            print(f"  ! {item.path}  [{'; '.join(extras)}]")

    migrated = report.by_action("migrate")
    if migrated:
        print("\nBy repository")
        print("─" * 40)
        grouped: dict[str, list] = defaultdict(list)
        for item in migrated:
            grouped[item.repo].append(item)
        for repo in sorted(grouped):
            items = grouped[repo]
            removed = sum(i.words_before - i.words_after for i in items)
            print(f"  {repo}: {len(items)} files, {removed} words removed")

    skipped = report.by_action("skipped")
    reasons: dict[str, int] = defaultdict(int)
    for item in skipped:
        reasons[item.reason] += 1
    if reasons or report.skipped_directories:
        print("\nSkipped")
        print("─" * 40)
        for reason in sorted(reasons):
            print(f"  {reason}: {reasons[reason]} files")
        if report.skipped_directories:
            print(f"  symlinked-directory: {len(report.skipped_directories)} directories")

    unchanged = report.by_action("unchanged")
    errors = report.by_action("error")
    removed_total = sum(i.words_before - i.words_after for i in migrated)
    print("\nTotals")
    print("─" * 40)
    print(f"  {'Migrated' if write else 'Would migrate'}: {len(migrated)} files")
    print(f"  Block words removed: {removed_total}")
    print(f"  Already pointers: {len(unchanged)}")
    print(f"  Skipped: {len(skipped)} files")
    if errors:
        print(f"  Errors: {len(errors)}")
        for item in errors:
            print(f"    - {item.path}: {item.reason}")
    if not write:
        print("\n[DRY RUN] No files were modified.")
    return 1 if errors else 0


def _change_marker(action: str) -> str:
    if action == "created":
        return "A"
    if action == "updated":
        return "M"
    return "?"

def cmd_context_diff(args: argparse.Namespace) -> int:
    import json

    from organvm_engine.paths import context_changelog_path

    changelog_file = context_changelog_path()
    if not changelog_file.is_file():
        print("No changelog found.")
        return 0

    last_n = getattr(args, "last", 1)

    # Read and group by timestamp
    syncs = {}
    with changelog_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                ts = record.get("timestamp")
                if ts:
                    if ts not in syncs:
                        syncs[ts] = []
                    syncs[ts].append(record)
            except Exception:
                pass

    if not syncs:
        print("No valid changelog records found.")
        return 0

    # Sort by timestamp descending
    sorted_ts = sorted(syncs.keys(), reverse=True)
    target_ts_list = sorted_ts[:last_n]

    import datetime

    for ts in target_ts_list:
        dt = datetime.datetime.fromtimestamp(ts)
        print(f"\nSync at {dt.isoformat()} (Timestamp: {ts})")
        print("=" * 60)

        for record in syncs[ts]:
            path = record.get("path")
            action = record.get("action")
            diff = record.get("diff")

            print(f"\n--- {path} ({action}) ---")
            if diff:
                print(diff)
            else:
                print("(No diff recorded or content created)")

    return 0

def cmd_context_rollback(args: argparse.Namespace) -> int:
    import json
    import re
    from pathlib import Path

    from organvm_engine.contextmd import AUTO_END, AUTO_START
    from organvm_engine.paths import context_changelog_path

    changelog_file = context_changelog_path()
    if not changelog_file.is_file():
        print("No changelog found.")
        return 1

    target_ts = int(args.to)

    records_to_rollback = []
    with changelog_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if record.get("timestamp") == target_ts:
                    records_to_rollback.append(record)
            except Exception:
                pass

    if not records_to_rollback:
        print(f"No records found for timestamp {target_ts}.")
        return 1

    print(f"Found {len(records_to_rollback)} records for timestamp {target_ts}. Rolling back...")

    for record in records_to_rollback:
        path = Path(record.get("path"))
        action = record.get("action")
        old_section = record.get("old_section", "")

        print(f"Rolling back {path} ({action})")

        if not path.is_file():
            print(f"  File {path} does not exist. Skipping.")
            continue

        if record.get("whole_file"):
            # A generator-owned file (docs/organvm-context.md) has no markers to
            # cut around: restore the previous bytes, or remove what was created.
            if action == "created":
                print(f"  Deleting generator-owned {path}.")
                path.unlink()
            elif action == "updated":
                path.write_text(old_section)
            else:
                print(f"  Unknown action {action} for {path}. Skipping.")
            continue

        content = path.read_text()

        if action == "created":
            if not old_section:
                # Need to be careful here to only remove the auto-generated section, or delete if empty
                if AUTO_START in content and AUTO_END in content:
                    pattern = re.escape(AUTO_START) + r".*" + re.escape(AUTO_END)
                    new_content = re.sub(pattern, "", content, flags=re.DOTALL)
                    new_content = new_content.strip()
                    if new_content:
                        path.write_text(new_content + "\n")
                    else:
                        print(f"  Deleting {path} as it only contained the generated section.")
                        path.unlink()
            else:
                print("  Unexpected: created action has old_section. Replacing block.")
                pattern = re.escape(AUTO_START) + r".*" + re.escape(AUTO_END)
                new_content = re.sub(pattern, old_section, content, flags=re.DOTALL)
                path.write_text(new_content)
        elif action == "updated":
            if AUTO_START in content and AUTO_END in content:
                pattern = re.escape(AUTO_START) + r".*" + re.escape(AUTO_END)
                new_content = re.sub(pattern, old_section, content, flags=re.DOTALL)
                path.write_text(new_content)
            else:
                print(f"  No AUTO block found in {path}. Skipping.")
        else:
            print(f"  Unknown action {action} for {path}. Skipping.")

    print("Rollback complete.")
    return 0
