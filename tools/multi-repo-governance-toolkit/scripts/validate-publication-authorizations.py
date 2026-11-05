#!/usr/bin/env python3
"""Validate ORGANVM publication authorization records and optional preflight requests."""
from __future__ import annotations
import argparse
import datetime as dt
import fnmatch
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "governance" / "publication-authorizations.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SURFACES = {"source", "package", "release", "site", "documentation", "dataset", "artifact", "container"}
STATUSES = {"draft", "approved", "revoked", "expired"}
REQUIRED = {"id", "repository_id", "formation_id", "revision", "paths", "surface", "destination", "license", "rights_authority", "approved_by", "benefit", "approved_at", "expires_at", "status"}

def parse_time(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed

def load_ledger(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("default") != "deny":
        raise ValueError("ledger default must be 'deny'")
    if not isinstance(data.get("authorizations"), list):
        raise ValueError("authorizations must be a list")
    return data

def validate_record(record: dict, seen: set[str]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED - record.keys())
    if missing:
        return [f"missing fields: {', '.join(missing)}"]
    record_id = record["id"]
    if not isinstance(record_id, str) or not record_id.strip():
        errors.append("id must be a non-empty string")
    elif record_id in seen:
        errors.append(f"duplicate id: {record_id}")
    else:
        seen.add(record_id)
    if not isinstance(record["repository_id"], (str, int)) or str(record["repository_id"]).strip() == "":
        errors.append("repository_id must be a stable GitHub repository ID")
    if not isinstance(record["formation_id"], str) or not record["formation_id"].strip():
        errors.append("formation_id must be a non-empty string")
    revision = record["revision"]
    if not isinstance(revision, str) or not (SHA_RE.fullmatch(revision) or SHA256_RE.fullmatch(revision)):
        errors.append("revision must be a lowercase 40-character commit SHA or 64-character digest")
    paths = record["paths"]
    if not isinstance(paths, list) or not paths or any(not isinstance(p, str) or not p.strip() for p in paths):
        errors.append("paths must be a non-empty string list")
    elif any(p in {"*", "**", "/"} for p in paths):
        errors.append("unbounded path authorization is forbidden")
    if record["surface"] not in SURFACES:
        errors.append(f"unsupported surface: {record['surface']}")
    if record["status"] not in STATUSES:
        errors.append(f"unsupported status: {record['status']}")
    for field in ("destination", "license", "rights_authority", "approved_by", "benefit"):
        if not isinstance(record[field], str) or not record[field].strip():
            errors.append(f"{field} must be a non-empty string")
    try:
        approved = parse_time(record["approved_at"])
        expires = parse_time(record["expires_at"])
        if expires <= approved:
            errors.append("expires_at must be later than approved_at")
    except (TypeError, ValueError) as exc:
        errors.append(f"invalid timestamp: {exc}")
    return errors

def authorize(records: list[dict], args: argparse.Namespace) -> bool:
    now = dt.datetime.now(dt.timezone.utc)
    for record in records:
        if record["status"] != "approved":
            continue
        if str(record["repository_id"]) != str(args.repository_id):
            continue
        if record["revision"] != args.revision or record["surface"] != args.surface:
            continue
        if parse_time(record["expires_at"]) <= now:
            continue
        if all(any(fnmatch.fnmatch(path, pattern) for pattern in record["paths"]) for path in args.path):
            return True
    return False

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--repository-id")
    parser.add_argument("--revision")
    parser.add_argument("--surface", choices=sorted(SURFACES))
    parser.add_argument("--path", action="append", default=[])
    args = parser.parse_args()
    try:
        ledger = load_ledger(args.ledger)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"publication ledger invalid: {exc}", file=sys.stderr)
        return 2
    seen: set[str] = set()
    errors: list[str] = []
    for index, record in enumerate(ledger["authorizations"]):
        if not isinstance(record, dict):
            errors.append(f"authorization[{index}]: must be an object")
            continue
        errors.extend(f"authorization[{index}]: {error}" for error in validate_record(record, seen))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    requested = any((args.repository_id, args.revision, args.surface, args.path))
    complete = all((args.repository_id, args.revision, args.surface)) and bool(args.path)
    if requested and not complete:
        print("preflight requires --repository-id, --revision, --surface, and at least one --path", file=sys.stderr)
        return 2
    if complete and not authorize(ledger["authorizations"], args):
        print("publication denied: no current authorization matches the exact request", file=sys.stderr)
        return 3
    print("publication authorization ledger valid" if not complete else "publication authorized")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
