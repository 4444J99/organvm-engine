"""Unit test suite for scripts/quality-filter.py logic and marker scanning."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

# Dynamically import scripts/quality-filter.py
SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "quality-filter.py"
spec = importlib.util.spec_from_file_location("quality_filter", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Could not load module specification from {SCRIPT_PATH}")
quality_filter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = quality_filter
spec.loader.exec_module(quality_filter)


class QualityFilterTests(unittest.TestCase):
    """Test suite for quality filter regex detection and classification logic."""

    def test_extract_extension(self) -> None:
        """Verify file extension extraction handling anchors and clean paths."""
        self.assertEqual(quality_filter.extract_extension("foo/bar/baz.py"), "py")
        self.assertEqual(quality_filter.extract_extension("types/index.d.ts#L10-L20"), "ts")
        self.assertEqual(quality_filter.extract_extension("README"), "")
        self.assertEqual(quality_filter.extract_extension("archive.tar.gz"), "gz")

    def test_is_code_artifact_by_source(self) -> None:
        """Verify classification of code artifact extensions and path noise patterns."""
        # Extensions flagged as noise in CODE_ARTIFACT_EXTENSIONS
        self.assertEqual(quality_filter.is_code_artifact_by_source("stubs/module.pyi"), "code_extension:pyi")
        self.assertEqual(quality_filter.is_code_artifact_by_source("stubs/module.pyc"), "code_extension:pyc")
        self.assertEqual(quality_filter.is_code_artifact_by_source("dist/app.map"), "code_extension:map")
        self.assertEqual(quality_filter.is_code_artifact_by_source("package.lock"), "code_extension:lock")
        self.assertEqual(quality_filter.is_code_artifact_by_source("module.wasm"), "code_extension:wasm")

        # Source path noise patterns
        self.assertIsNotNone(quality_filter.is_code_artifact_by_source("typeshed-fallback/stdlib/os.pyi"))
        self.assertIsNotNone(quality_filter.is_code_artifact_by_source("node_modules/express/index.js"))
        self.assertIsNotNone(quality_filter.is_code_artifact_by_source(".vscode/extensions/ms-python.python/out.js"))
        self.assertIsNotNone(quality_filter.is_code_artifact_by_source("project/.git/hooks/pre-commit"))
        self.assertIsNotNone(quality_filter.is_code_artifact_by_source("build/dist/bundle.js"))

        # Normal files should not be flagged by source path
        self.assertIsNone(quality_filter.is_code_artifact_by_source("docs/architecture.md"))
        self.assertIsNone(quality_filter.is_code_artifact_by_source("src/main.py"))

    def test_todo_fixme_hack_detection(self) -> None:
        """Verify regex detection for TODO/FIXME/HACK/XXX/UNDONE code markers."""
        seen_hashes: dict[str, str] = {}

        markers = ["TODO", "FIXME", "HACK", "XXX", "UNDONE"]
        for marker in markers:
            atom = {
                "id": f"atom-{marker}",
                "label": "TODO",
                "source_file": "src/utils.py",
                "context": f"# {marker}: refactor this function for better performance in the long run",
            }
            res = quality_filter.classify_atom(atom, seen_hashes.copy())
            self.assertTrue(res.is_noise)
            self.assertIn("todo_in_code", res.reasons)

        # C-style comment markers
        atom_c_style = {
            "id": "atom-c-style",
            "label": "HACK",
            "source_file": "src/module.js",
            "context": "/* HACK: temporary workaround for browser compatibility bug */",
        }
        res_c = quality_filter.classify_atom(atom_c_style, seen_hashes.copy())
        self.assertTrue(res_c.is_noise)
        self.assertIn("todo_in_code", res_c.reasons)

    def test_false_positive_scenarios_tbd_docstrings_prose(self) -> None:
        """Verify known false-positive scenarios (TBD in docstrings, prose TODOs) remain signal."""
        seen_hashes: dict[str, str] = {}

        # TBD mentions in prose documentation or docstrings
        tbd_atom = {
            "id": "atom-tbd-prose",
            "label": "TBD",
            "source_file": "docs/specification.md",
            "context": "The specification details for the external authentication subsystem are TBD pending security review.",
        }
        res_tbd = quality_filter.classify_atom(tbd_atom, seen_hashes.copy())
        self.assertFalse(res_tbd.is_noise)
        self.assertEqual(res_tbd.reasons, [])

        # Prose mentions of TODO without comment characters (//, #, /*)
        prose_todo_atom = {
            "id": "atom-prose-todo",
            "label": "TODO",
            "source_file": "docs/planning.md",
            "context": "This document outlines the primary TODO items and milestone achievements for Q3 governance roadmap.",
        }
        res_todo = quality_filter.classify_atom(prose_todo_atom, seen_hashes.copy())
        self.assertFalse(res_todo.is_noise)
        self.assertEqual(res_todo.reasons, [])

    def test_noise_categories_classification(self) -> None:
        """Verify specific context noise category patterns."""
        seen_hashes: dict[str, str] = {}

        test_cases: list[tuple[str, str, str]] = [
            ("python_type_hint", "def get_name(user_id: int) -> str | None:", "src/user.py"),
            ("ts_type_annotation", "const value: string | undefined = getVal();", "src/index.ts"),
            ("js_undefined_check", "if (typeof config === 'undefined') return;", "src/config.js"),
            ("code_null_check", "if (result !== null && result.isValid) {", "src/check.js"),
            ("python_none_code", "val = None, # default fallback value", "src/params.py"),
            ("css_none_value", "div.hidden-modal { display: none; }", "styles/app.css"),
            ("html_markup", "<div class=\"container\"><span>Content</span></div>", "views/index.html"),
            ("shell_devnull", "echo 'quiet' > /dev/null 2>&1", "scripts/deploy.sh"),
            ("job_boilerplate", "Equal Opportunity Employer M/F/D/V. Bachelor's degree required.", "careers/posting.md"),
            ("json_schema_null", '"type": null, "description": "optional configuration object"', "schemas/config.json"),
            ("minified_code", "//# sourceMappingURL=bundle.min.js.map", "dist/bundle.js"),
        ]

        for expected_reason, context, source_file in test_cases:
            atom = {
                "id": f"atom-{expected_reason}",
                "label": "UNKNOWN",
                "source_file": source_file,
                "context": context,
            }
            res = quality_filter.classify_atom(atom, seen_hashes.copy())
            self.assertTrue(res.is_noise, f"Failed to detect {expected_reason} in '{context}'")
            self.assertIn(expected_reason, res.reasons)

    def test_too_short_context_and_duplicates(self) -> None:
        """Verify detection of contexts that are too short or duplicate context hashes."""
        seen_hashes: dict[str, str] = {}

        # Too short context
        short_atom = {
            "id": "atom-short",
            "label": "N/A",
            "source_file": "docs/note.txt",
            "context": "n/a foo",
        }
        res_short = quality_filter.classify_atom(short_atom, seen_hashes)
        self.assertTrue(res_short.is_noise)
        self.assertIn("too_short", res_short.reasons)

        # Duplicate context
        atom1 = {
            "id": "atom-orig",
            "label": "N/A",
            "source_file": "docs/chapter1.md",
            "context": "This is a detailed analysis of the systemic requirements and governance guidelines.",
        }
        atom2 = {
            "id": "atom-dup",
            "label": "N/A",
            "source_file": "docs/chapter2.md",
            "context": "This is a detailed analysis of the systemic requirements and governance guidelines.",
        }

        res1 = quality_filter.classify_atom(atom1, seen_hashes)
        self.assertFalse(res1.is_noise)

        res2 = quality_filter.classify_atom(atom2, seen_hashes)
        self.assertTrue(res2.is_noise)
        self.assertIn("duplicate_of:atom-orig", res2.reasons)

    def test_programming_keyword_labels_in_code_context(self) -> None:
        """Verify programming keyword labels (None, null, undefined) in code files with code indicators."""
        seen_hashes: dict[str, str] = {}

        code_atom = {
            "id": "atom-code-keyword",
            "label": "None",
            "source_file": "src/handler.py",
            "context": "def handle_request(self):\n    if self.data is None:\n        return None",
        }

        res = quality_filter.classify_atom(code_atom, seen_hashes)
        self.assertTrue(res.is_noise)
        self.assertTrue(any("code_context_None" in r or "python_none_code" in r for r in res.reasons))

    def test_run_filter_end_to_end(self) -> None:
        """Verify run_filter reads input JSONL and writes signal/noise files and computes stats."""
        atoms: list[dict[str, Any]] = [
            # Signal 1
            {
                "id": "sig-1",
                "label": "TBD",
                "source_file": "docs/architecture.md",
                "context": "The system topology contract details are TBD pending final signoff from governance.",
            },
            # Signal 2
            {
                "id": "sig-2",
                "label": "TODO",
                "source_file": "specs/roadmap.md",
                "context": "Review the section regarding cross-organ synchronization protocol and update metrics.",
            },
            # Noise 1 (code comment marker)
            {
                "id": "noise-1",
                "label": "TODO",
                "source_file": "scripts/build.py",
                "context": "# TODO: add error handling for missing configuration parameters in build",
            },
            # Noise 2 (duplicate of Signal 1)
            {
                "id": "noise-dup",
                "label": "TBD",
                "source_file": "docs/architecture_backup.md",
                "context": "The system topology contract details are TBD pending final signoff from governance.",
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            input_file = tmp_path / "vacuum-atoms.jsonl"
            with open(input_file, "w", encoding="utf-8") as f:
                for a in atoms:
                    f.write(json.dumps(a) + "\n")

            # Run in dry run mode
            dry_stats = quality_filter.run_filter(input_file, output_dir=tmp_path, dry_run=True)
            self.assertEqual(dry_stats.total, 4)
            self.assertEqual(dry_stats.signal, 2)
            self.assertEqual(dry_stats.noise, 2)

            # Run actual filter execution
            stats = quality_filter.run_filter(input_file, output_dir=tmp_path, dry_run=False)
            self.assertEqual(stats.total, 4)
            self.assertEqual(stats.signal, 2)
            self.assertEqual(stats.noise, 2)

            signal_file = tmp_path / "vacuum-atoms-signal.jsonl"
            noise_file = tmp_path / "vacuum-atoms-noise.jsonl"

            self.assertTrue(signal_file.exists())
            self.assertTrue(noise_file.exists())

            with open(signal_file, "r", encoding="utf-8") as f:
                signal_lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(signal_lines), 2)
            self.assertEqual({s["id"] for s in signal_lines}, {"sig-1", "sig-2"})

            with open(noise_file, "r", encoding="utf-8") as f:
                noise_lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(noise_lines), 2)
            self.assertEqual({n["id"] for n in noise_lines}, {"noise-1", "noise-dup"})


if __name__ == "__main__":
    unittest.main()
