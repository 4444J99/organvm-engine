import importlib.util, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "identity-lint.py"
spec = importlib.util.spec_from_file_location("identity_lint", SCRIPT)
il = importlib.util.module_from_spec(spec); sys.modules["identity_lint"] = il; spec.loader.exec_module(il)

SALT = "fixture-salt-0123456789abcdef"
ENV_KEYS = ("IDENTITY_SALT", "IDENTITY_DENYLIST", "IDENTITY_OWN_NAMES", "IDENTITY_DENY_DOMAINS")


def make(tmp, files, allow=""):
    for k, v in files.items():
        p = tmp / k; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(v)
    (tmp / ".identity-allow").write_text(allow)
    return tmp


def run(tmp, deny=(), own=(), env=None, salt=SALT):
    e = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    if salt is not None:
        e["IDENTITY_SALT"] = salt
    if deny:
        e["IDENTITY_DENYLIST"] = "\n".join(il.term_hash(t, SALT) for t in deny)
    if own:
        e["IDENTITY_OWN_NAMES"] = "\n".join(own)
    e.update(env or {})
    return subprocess.run([sys.executable, str(SCRIPT), str(tmp)], capture_output=True, text=True, env=e)


def test_normalize_and_salted_hash():
    assert il.normalize("Jane-Doe, Inc.") == ["jane", "doe", "inc"]
    assert il.term_hash("Jane  DOE", SALT) == il.term_hash("jane-doe", SALT)
    assert il.term_hash("jane doe", SALT) != il.term_hash("jane doe", "other")
    import hashlib
    assert il.term_hash("jane doe", SALT) == hashlib.sha256((SALT + "jane doe").encode()).hexdigest()


def test_ngram_match_and_no_plaintext_leak(tmp_path):
    make(tmp_path, {"a.md": "Work for Acme Widget Co today\n"})
    r = run(tmp_path, deny=["acme widget co"])
    assert r.returncode == 1 and "a.md:1: [denylist]" in r.stdout
    assert "acme" not in r.stdout.lower()


def test_wrong_salt_does_not_match(tmp_path):
    make(tmp_path, {"a.md": "Zed Quux\n"})
    assert run(tmp_path, deny=["zed quux"], salt="different").returncode == 0


def test_whole_word_only(tmp_path):
    make(tmp_path, {"a.md": "zedx azed zedonk\n"})
    assert run(tmp_path, deny=["zed"]).returncode == 0
    make(tmp_path, {"a.md": "thanks Zed.\n"})
    assert run(tmp_path, deny=["zed"]).returncode == 1


def test_missing_config_skips_hash_check(tmp_path):
    make(tmp_path, {"a.md": "Zed Quux me@gmail.com\n"})
    r = run(tmp_path, deny=["zed quux"], salt=None)
    assert "notice" in r.stdout and "[denylist]" not in r.stdout and "[email]" in r.stdout
    r = run(tmp_path)
    assert "notice" in r.stdout and "[email]" in r.stdout


def test_bad_denylist_hash(tmp_path):
    make(tmp_path, {"a.md": "x\n"})
    assert run(tmp_path, env={"IDENTITY_DENYLIST": "nothex"}).returncode != 0


def test_emails(tmp_path):
    make(tmp_path, {"a.md": "a@users.noreply.github.com b@example.org c@mail.example.co.uk\n"})
    assert run(tmp_path).returncode == 0
    make(tmp_path, {"a.md": "me@gmail.com\n"})
    assert "[email]" in run(tmp_path).stdout


def test_home_paths(tmp_path):
    for s in ["/Users/x/a", "/home/x", "~/Workspace/y", "~/Code/z"]:
        make(tmp_path, {"a.md": s + "\n"})
        assert "[home-path]" in run(tmp_path).stdout, s


def test_personal_domain(tmp_path):
    make(tmp_path, {"a.md": "see zedquux.dev\n"})
    assert "[domain]" in run(tmp_path, deny=["zedquux"]).stdout
    make(tmp_path, {"a.md": "see other.dev\n"})
    assert run(tmp_path, env={"IDENTITY_DENY_DOMAINS": "other.dev"}).returncode == 1


def test_allowlist_and_own_names(tmp_path):
    make(tmp_path, {"LICENSE": "Copyright (c) 2026 Zed Quux\nZed Quux\n"},
         allow="denylist LICENSE ^Copyright  # MIT\n")
    r = run(tmp_path, deny=["zed quux"])
    assert r.returncode == 1 and "LICENSE:2" in r.stdout and "LICENSE:1" not in r.stdout
    make(tmp_path, {"a.md": "by myorg\n"})
    assert run(tmp_path, deny=["myorg"], own=["myorg"]).returncode == 0


def test_hash_stdin():
    e = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    e["IDENTITY_SALT"] = SALT
    r = subprocess.run([sys.executable, str(SCRIPT), "--hash-stdin"], input="Zed Quux\n",
                       capture_output=True, text=True, env=e)
    assert r.stdout.strip() == il.term_hash("zed quux", SALT)


def test_allowlist_requires_reason(tmp_path):
    make(tmp_path, {"a.md": "x\n"}, allow="email a.md .\n")
    assert run(tmp_path).returncode != 0


def test_repo_is_clean():
    assert run(ROOT, salt=None).returncode == 0
