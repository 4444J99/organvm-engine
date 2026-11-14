"""Tests for the public CLI surface inventory and compatibility classification."""

import argparse
import copy
import re
from pathlib import Path

import pytest

from organvm_engine import __version__
from organvm_engine.api_surface import (
    SCHEMA_VERSION,
    baseline_path,
    diff_surfaces,
    extract_surface,
    load_baseline,
    main,
    render_surface,
)
from organvm_engine.cli import build_parser

REPO_ROOT = Path(__file__).resolve().parents[1]


def _toy_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="toy")
    sub = p.add_subparsers(dest="cmd")
    run = sub.add_parser("run")
    run.add_argument("target")
    run.add_argument("--mode", choices=["fast", "slow"], default="fast")
    run.add_argument("--json", action="store_true")
    grp = sub.add_parser("grp")
    gsub = grp.add_subparsers(dest="sub")
    gsub.add_parser("list").add_argument("--limit", type=int)
    return p


class TestExtract:
    def test_nested_commands_and_arguments(self):
        s = extract_surface(_toy_parser())
        assert set(s["commands"]) == {"run", "grp", "grp list"}  # no root args here
        run = s["commands"]["run"]["arguments"]
        assert run["target"] == {
            "required": True, "takes_value": True, "nargs": "1", "position": 0,
        }
        assert run["--mode"]["choices"] == ["fast", "slow"]
        assert run["--mode"]["required"] is False
        assert run["--json"]["takes_value"] is False

    def test_help_action_excluded(self):
        s = extract_surface(_toy_parser())
        assert all("--help" not in c["arguments"] for c in s["commands"].values())

    def test_deterministic(self):
        assert render_surface(extract_surface(_toy_parser())) == render_surface(
            extract_surface(_toy_parser()),
        )


class TestDiff:
    def _base(self):
        return extract_surface(_toy_parser())

    def test_identical_is_empty(self):
        assert diff_surfaces(self._base(), self._base()).is_empty

    def test_removed_command_is_breaking(self):
        cur = self._base()
        del cur["commands"]["grp list"]
        d = diff_surfaces(self._base(), cur)
        assert d.is_breaking
        assert "command removed: grp list" in d.breaking

    def test_added_command_is_compatible(self):
        cur = self._base()
        cur["commands"]["new"] = {"arguments": {}}
        d = diff_surfaces(self._base(), cur)
        assert not d.is_breaking
        assert d.compatible == ["command added: new"]

    def test_removed_argument_and_flag_are_breaking(self):
        cur = self._base()
        del cur["commands"]["run"]["arguments"]["--json"]
        assert "argument removed: run --json" in diff_surfaces(self._base(), cur).breaking

    def test_new_required_argument_is_breaking_optional_is_compatible(self):
        cur = self._base()
        cur["commands"]["run"]["arguments"]["--must"] = {
            "required": True, "takes_value": True, "flags": ["--must"],
        }
        cur["commands"]["run"]["arguments"]["--may"] = {
            "required": False, "takes_value": True, "flags": ["--may"],
        }
        d = diff_surfaces(self._base(), cur)
        assert "required argument added: run --must" in d.breaking
        assert "argument added: run --may" in d.compatible

    def test_became_required_is_breaking(self):
        cur = copy.deepcopy(self._base())
        cur["commands"]["grp list"]["arguments"]["--limit"]["required"] = True
        assert "argument became required: grp list --limit" in (
            diff_surfaces(self._base(), cur).breaking
        )

    def test_choice_removed_breaking_choice_added_compatible(self):
        cur = copy.deepcopy(self._base())
        cur["commands"]["run"]["arguments"]["--mode"]["choices"] = ["fast", "turbo"]
        d = diff_surfaces(self._base(), cur)
        assert "choice removed: run --mode=slow" in d.breaking
        assert "choice added: run --mode=turbo" in d.compatible

    def test_arity_change_is_breaking(self):
        cur = copy.deepcopy(self._base())
        cur["commands"]["run"]["arguments"]["--json"]["takes_value"] = True
        assert "argument value arity changed: run --json" in (
            diff_surfaces(self._base(), cur).breaking
        )


class TestReviewedCounterexamples:
    """Counterexamples raised in review of the first revision."""

    @staticmethod
    def _parser(builder):
        p = argparse.ArgumentParser(prog="toy")
        p.add_argument("--registry")
        sub = p.add_subparsers(dest="cmd")
        builder(sub)
        return p

    def test_root_level_option_removed_is_breaking(self):
        base = extract_surface(self._parser(lambda sub: sub.add_parser("a")))
        bare = argparse.ArgumentParser(prog="toy")
        bare.add_subparsers(dest="cmd").add_parser("a")
        cur = extract_surface(bare)
        assert "--registry" in base["commands"]["(root)"]["arguments"]
        assert "argument removed: (root) --registry" in diff_surfaces(base, cur).breaking

    def test_root_option_made_required_is_breaking(self):
        base = extract_surface(self._parser(lambda sub: sub.add_parser("a")))
        p = argparse.ArgumentParser(prog="toy")
        p.add_argument("--registry", required=True)
        p.add_subparsers(dest="cmd").add_parser("a")
        d = diff_surfaces(base, extract_surface(p))
        assert "argument became required: (root) --registry" in d.breaking

    def test_nargs_plus_to_single_is_breaking(self):
        def many(sub):
            sub.add_parser("merge").add_argument("sources", nargs="+")

        def one(sub):
            sub.add_parser("merge").add_argument("sources")

        d = diff_surfaces(
            extract_surface(self._parser(many)), extract_surface(self._parser(one)),
        )
        assert any(line.startswith("argument cardinality changed: merge sources") for line in d.breaking)

    def test_adding_longer_alias_is_compatible(self):
        def before(sub):
            sub.add_parser("run").add_argument("--mode", dest="mode")

        def after(sub):
            sub.add_parser("run").add_argument("--mode", "--execution-mode", dest="mode")

        d = diff_surfaces(
            extract_surface(self._parser(before)), extract_surface(self._parser(after)),
        )
        assert not d.breaking, d.breaking
        assert "flag added: run --execution-mode" in d.compatible

    def test_removing_alias_keeps_argument_but_flags_break(self):
        def before(sub):
            sub.add_parser("run").add_argument("--mode", "--execution-mode", dest="mode")

        def after(sub):
            sub.add_parser("run").add_argument("--mode", dest="mode")

        d = diff_surfaces(
            extract_surface(self._parser(before)), extract_surface(self._parser(after)),
        )
        assert d.breaking == ["flag removed: run --execution-mode"]

    def test_positional_reorder_is_breaking(self):
        def before(sub):
            c = sub.add_parser("update")
            c.add_argument("field")
            c.add_argument("value")

        def after(sub):
            c = sub.add_parser("update")
            c.add_argument("value")
            c.add_argument("field")

        d = diff_surfaces(
            extract_surface(self._parser(before)), extract_surface(self._parser(after)),
        )
        assert "positional order changed: update field 0 -> 1" in d.breaking
        assert "positional order changed: update value 1 -> 0" in d.breaking

    def test_live_parser_has_root_registry_option(self):
        root = extract_surface(build_parser())["commands"]["(root)"]["arguments"]
        assert "--registry" in root


class TestBaselineContract:
    def test_schema_version_rejected_when_unknown(self, tmp_path):
        p = tmp_path / "b.json"
        p.write_text('{"schema_version": 999, "commands": {}}')
        with pytest.raises(ValueError, match="unsupported schema_version"):
            load_baseline(p)

    def test_committed_baseline_has_no_breaking_drift(self):
        baseline = load_baseline(baseline_path(REPO_ROOT))
        assert baseline["schema_version"] == SCHEMA_VERSION
        diff = diff_surfaces(baseline, extract_surface(build_parser()))
        assert not diff.breaking, "\n".join(diff.breaking)

    def test_baseline_covers_known_roots(self):
        cmds = load_baseline(baseline_path(REPO_ROOT))["commands"]
        assert {"registry", "governance", "seed"} <= set(cmds)

    def test_check_exit_codes(self, tmp_path, capsys):
        base = extract_surface(build_parser())
        stale = copy.deepcopy(base)
        stale["commands"]["definitely-removed"] = {"arguments": {}}
        path = tmp_path / "b.json"
        path.write_text(render_surface(stale))
        assert main(["check", "--baseline", str(path)]) == 1
        assert "BREAKING   command removed: definitely-removed" in capsys.readouterr().out

        path.write_text(render_surface(base))
        assert main(["check", "--baseline", str(path)]) == 0

        assert main(["check", "--baseline", str(tmp_path / "missing.json")]) == 2

    def test_write_roundtrip(self, tmp_path):
        path = tmp_path / "sub" / "b.json"
        assert main(["write", "--baseline", str(path)]) == 0
        assert main(["check", "--baseline", str(path)]) == 0


def test_package_version_matches_metadata():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert m, "pyproject.toml declares no version"
    assert m.group(1) == __version__
