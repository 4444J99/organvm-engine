#!/usr/bin/env python3
"""Name-and-identity lint (salted mode).

Checks:
  denylist  - any token or n-gram (1-3 words) whose salted SHA-256
              sha256(salt + normalized term) is in the denylist
  email     - email addresses other than noreply / example.* domains
  home-path - absolute home paths (/Users/, /home/, ~/Workspace, ~/Code)
  domain    - personal domains (any domain whose labels hit the denylist,
              or listed in IDENTITY_DENY_DOMAINS)

Configuration comes only from the environment (CI passes repo secrets);
no denylist or name list is ever committed:
  IDENTITY_SALT       secret salt (hex or any string)
  IDENTITY_DENYLIST   newline/comma-separated salted hex hashes
  IDENTITY_OWN_NAMES  optional plaintext public names of this project/owner,
                      newline/comma-separated; never flagged
  IDENTITY_DENY_DOMAINS optional comma-separated domains

When IDENTITY_SALT or IDENTITY_DENYLIST is absent (forks, local runs) the
hash checks are skipped with a notice; the plain-pattern checks still run.
Matched terms are never printed; findings show only file, line and rule.

Normalization: lowercase, split on anything not [a-z0-9], join words with a
single space. So "Jane-Doe" -> "jane doe". Matching is whole-word.

Allowlist (.identity-allow), one entry per line:
    <rule> <path-glob> <line-regex>  # reason (required)
rule is one of denylist|email|home-path|domain|*.

Exit codes: 0 clean, 1 findings, 2 usage/config error.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MAX_N = 3
WORD_RE = re.compile(r"[a-z0-9]+")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")
HOME_RE = re.compile(r"(/Users/|/home/|~/Workspace\b|~/Code\b)")
DOMAIN_RE = re.compile(r"\b((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})\b")
RULES = {"denylist", "email", "home-path", "domain"}


def normalize(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def term_hash(term: str, salt: str) -> str:
    return salted(" ".join(normalize(term)), salt)


def salted(normalized: str, salt: str) -> str:
    return hashlib.sha256((salt + normalized).encode()).hexdigest()


def ngrams(words: list[str], max_n: int = MAX_N):
    for n in range(1, max_n + 1):
        for i in range(len(words) - n + 1):
            yield " ".join(words[i : i + n])


def email_allowed(addr: str, domain: str) -> bool:
    d = domain.lower()
    local = addr.split("@", 1)[0].lower()
    if "noreply" in local or "no-reply" in local or "noreply" in d:
        return True
    labels = d.split(".")
    return "example" in labels[:-1] or d in {"example", "localhost"}


@dataclass
class Allow:
    rule: str
    glob: str
    regex: re.Pattern
    reason: str

    def matches(self, rule: str, path: str, line: str) -> bool:
        return (self.rule in ("*", rule)) and fnmatch.fnmatch(path, self.glob) and bool(self.regex.search(line))


def load_allow(path: Path) -> list[Allow]:
    out: list[Allow] = []
    if not path.exists():
        return out
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        body, _, reason = s.partition("#")
        parts = body.split(None, 2)
        if len(parts) != 3 or not reason.strip():
            raise SystemExit(f"{path}:{n}: need '<rule> <glob> <regex>  # reason'")
        rule, glob, rx = parts
        if rule != "*" and rule not in RULES:
            raise SystemExit(f"{path}:{n}: unknown rule {rule!r}")
        out.append(Allow(rule, glob, re.compile(rx.strip()), reason.strip()))
    return out


def split_env(name: str) -> list[str]:
    return [t.strip() for t in re.split(r"[,\n]", os.environ.get(name, "")) if t.strip()]


def load_hashes() -> set[str]:
    hs: set[str] = set()
    for s in split_env("IDENTITY_DENYLIST"):
        s = s.lower()
        if not re.fullmatch(r"[0-9a-f]{64}", s):
            raise SystemExit("IDENTITY_DENYLIST: bad hash line")
        hs.add(s)
    return hs


def load_own(salt: str) -> set[str]:
    return {term_hash(t, salt) for t in split_env("IDENTITY_OWN_NAMES") if normalize(t)}


def list_files(root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=root,
                             capture_output=True, text=True, check=True).stdout
        files = [f for f in out.splitlines() if f]
    except (subprocess.CalledProcessError, FileNotFoundError):
        files = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]
    return sorted(files)


SKIP: set[str] = set()


def scan(root: Path, hashes: set[str], allow: list[Allow], deny_domains: set[str], salt: str = ""):
    findings = []
    for rel in list_files(root):
        if rel in SKIP:
            continue
        p = root / rel
        try:
            data = p.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue
        text = data.decode("utf-8", "replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            hits = []
            if hashes:
                for g in set(ngrams(normalize(line))):
                    if salted(g, salt) in hashes:
                        hits.append(("denylist", "denylisted term"))
            for m in EMAIL_RE.finditer(line):
                if not email_allowed(m.group(0), m.group(1)):
                    hits.append(("email", "email address"))
            for m in HOME_RE.finditer(line):
                hits.append(("home-path", f"home path {m.group(1)!r}"))
            for m in DOMAIN_RE.finditer(line):
                d = m.group(1).lower()
                if d in deny_domains or any(
                    hashes and salted(lbl, salt) in hashes for lbl in normalize(d)
                ):
                    hits.append(("domain", "personal domain"))
            for rule, msg in hits:
                if not any(a.matches(rule, rel, line) for a in allow):
                    findings.append((rel, lineno, rule, msg))
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--allow", default=".identity-allow")
    ap.add_argument("--hash-stdin", action="store_true",
                    help="read terms (one per line) from stdin, print salted hashes using IDENTITY_SALT, exit")
    a = ap.parse_args(argv)
    salt = os.environ.get("IDENTITY_SALT", "")
    if a.hash_stdin:
        if not salt:
            print("identity-lint: IDENTITY_SALT is required for --hash-stdin", file=sys.stderr)
            return 2
        for t in sys.stdin.read().splitlines():
            if normalize(t):
                print(term_hash(t, salt))
        return 0
    root = Path(a.root).resolve()
    hashes = load_hashes()
    if salt and hashes:
        hashes -= load_own(salt)
    else:
        print("identity-lint: notice: IDENTITY_SALT/IDENTITY_DENYLIST not set; "
              "skipping denylist and domain-hash checks (plain-pattern checks still run)")
        hashes = set()
    allow = load_allow(root / a.allow)
    deny_domains = {d.strip().lower() for d in os.environ.get("IDENTITY_DENY_DOMAINS", "").split(",") if d.strip()}
    findings = scan(root, hashes, allow, deny_domains, salt)
    for rel, n, rule, msg in findings:
        print(f"{rel}:{n}: [{rule}] {msg}")
    print(f"identity-lint: {len(hashes)} denylist hashes, {len(allow)} allowlist entries, "
          f"{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
