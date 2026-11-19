"""Tests for corpus render indices (IRF-SYS-104, issue #81).

Validates that ``organvm corpus render`` publishes the six navigable
markdown indices from the same graph the scanner builds, deterministically
(sorted output, no timestamps), and that the CLI wires the new subcommand
through the parser and dispatch table.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from test_corpus import (
    _make_layer2,
    _make_seed_with_implements,
    _make_sidecar,
)

from organvm_engine.cli import build_parser, main
from organvm_engine.cli.corpus import cmd_corpus_render
from organvm_engine.corpus.graph import CorpusGraph, GraphEdge, GraphNode
from organvm_engine.corpus.render import (
    RENDER_FILES,
    render_all,
    render_concept_index,
    render_cross_corpus_bridges,
    render_gaps,
    render_provenance_map,
    render_spec_coverage,
    render_tag_analysis,
)
from organvm_engine.corpus.scanner import scan_corpus

# ── Fixtures ──────────────────────────────────────────────


def _make_graph(tmp_path: Path) -> CorpusGraph:
    """Full fixture graph: 2 concepts, 1 implemented, 1 orphan."""
    corpus_dir = _make_sidecar(tmp_path)
    _make_layer2(corpus_dir)
    _make_seed_with_implements(tmp_path)
    return scan_corpus(corpus_dir, workspace_root=tmp_path)


def _make_corpus_dir(tmp_path: Path) -> Path:
    corpus_dir = _make_sidecar(tmp_path)
    _make_layer2(corpus_dir)
    _make_seed_with_implements(tmp_path)
    return corpus_dir


def _make_bridge_graph() -> CorpusGraph:
    """Two concepts in different trunks sharing one transcript."""
    graph = CorpusGraph()
    graph.add_node(GraphNode(
        uid="concept:alpha", node_type="concept", title="alpha",
        metadata={"description": "Alpha", "trunks": ["A"],
                  "primary_source": "TRX-1"},
    ))
    graph.add_node(GraphNode(
        uid="concept:beta", node_type="concept", title="beta",
        metadata={"description": "Beta", "trunks": ["B"],
                  "primary_source": "TRX-1"},
    ))
    graph.add_node(GraphNode(
        uid="concept:gamma", node_type="concept", title="gamma",
        metadata={"description": "Gamma", "trunks": ["A", "B"],
                  "primary_source": "TRX-1"},
    ))
    graph.add_node(GraphNode(
        uid="concept:svse_engine", node_type="concept", title="svse_engine",
        metadata={"description": "SVSE engine", "trunks": ["SVSE"],
                  "primary_source": "TRX-1"},
    ))
    graph.add_node(GraphNode(
        uid="TRX-1", node_type="transcript", title="Shared Transcript",
    ))
    for concept in ("alpha", "beta", "gamma", "svse_engine"):
        graph.add_edge(GraphEdge(
            source="TRX-1", target=f"concept:{concept}",
            edge_type="DEFINES",
        ))
    return graph


# ── render_all ────────────────────────────────────────────


class TestRenderAll:
    def test_returns_all_six_files(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        rendered = render_all(graph)
        assert tuple(rendered) == RENDER_FILES
        for name in RENDER_FILES:
            assert rendered[name].startswith("# "), name
            assert len(rendered[name]) > 0

    def test_is_deterministic(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        assert render_all(graph) == render_all(graph)

    def test_empty_graph_renders(self) -> None:
        rendered = render_all(CorpusGraph())
        assert "No concepts in this graph" in rendered["concept-index.md"]
        assert "No concepts in this graph" in rendered["provenance-map.md"]
        assert "No concepts in this graph" in rendered["spec-coverage.md"]

    def test_single_concept_subset(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        rendered = render_all(graph, concept="test_concept")
        assert "test_concept" in rendered["concept-index.md"]
        assert "orphan_concept" not in rendered["concept-index.md"]
        assert "orphan_concept" not in rendered["provenance-map.md"]

    def test_single_concept_subset_accepts_prefix(
        self, tmp_path: Path,
    ) -> None:
        graph = _make_graph(tmp_path)
        rendered = render_all(graph, concept="concept:test_concept")
        assert "test_concept" in rendered["concept-index.md"]
        assert "orphan_concept" not in rendered["concept-index.md"]

    def test_unknown_concept_raises(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        with pytest.raises(ValueError, match="not found"):
            render_all(graph, concept="nonexistent")


# ── Individual indices ────────────────────────────────────


class TestConceptIndex:
    def test_lists_every_concept_sorted(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        text = render_concept_index(graph)
        assert text.index("orphan_concept") < text.index("test_concept")
        assert "A test concept for validation" in text
        assert "A concept with no implementation" in text

    def test_shows_primary_source(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        text = render_concept_index(graph)
        assert "TRX-TEST" in text


class TestProvenanceMap:
    def test_implemented_concept_lists_repo(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        text = render_provenance_map(graph)
        assert "## test_concept" in text
        assert "test-repo" in text
        assert "Test implementation aspect" in text

    def test_orphan_concept_is_marked_gap(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        text = render_provenance_map(graph)
        assert "## orphan_concept" in text
        assert "[GAP] No implementations found." in text


class TestSpecCoverage:
    def test_numbers_match_coverage_depth(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        text = render_spec_coverage(graph)
        depth = {d["concept"]: d for d in graph.coverage_depth()}
        assert depth["orphan_concept"]["implementations"] == 0
        assert depth["orphan_concept"]["fragile"] is True
        assert depth["test_concept"]["implementations"] == 1
        # Fragile row first (coverage_depth sorts by fragility).
        assert text.index("orphan_concept") < text.index("test_concept")
        assert "| orphan_concept | 0 |" in text
        assert "| test_concept | 1 | test-repo |" in text


class TestTagAnalysis:
    def test_concepts_by_trunk(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        text = render_tag_analysis(graph)
        assert "| TEST | 2 |" in text

    def test_documents_by_tag(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        text = render_tag_analysis(graph)
        assert "| test | 1 |" in text


class TestCrossCorpusBridges:
    def test_fixture_has_no_bridges(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        text = render_cross_corpus_bridges(graph)
        assert "No multi-trunk concepts in this graph." in text
        assert "No cross-trunk concept pairs in this graph." in text

    def test_multi_trunk_concept_listed(self) -> None:
        graph = _make_bridge_graph()
        text = render_cross_corpus_bridges(graph)
        assert "gamma" in text
        assert "A, B" in text

    def test_shared_transcript_pair_listed(self) -> None:
        graph = _make_bridge_graph()
        text = render_cross_corpus_bridges(graph)
        assert "alpha" in text and "beta" in text
        assert "TRX-1" in text


class TestGaps:
    def test_lists_orphan_concept(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        text = render_gaps(graph)
        assert "orphan_concept" in text

    def test_absent_named_area_reported_as_absent(
        self, tmp_path: Path,
    ) -> None:
        graph = _make_graph(tmp_path)
        text = render_gaps(graph)
        assert "SVSE: named in the issue but absent from this graph" in text

    def test_present_unimplemented_named_area_is_confirmed_gap(self) -> None:
        graph = _make_bridge_graph()
        text = render_gaps(graph)
        assert "SVSE: `svse_engine` is present and unimplemented" in text


# ── CLI ───────────────────────────────────────────────────


class TestCorpusRenderCli:
    def test_help_parses(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["corpus", "render", "--help"])
        assert exc.value.code == 0

    def test_renders_six_files(self, tmp_path: Path) -> None:
        corpus_dir = _make_corpus_dir(tmp_path)
        out_dir = tmp_path / "indices"
        args = build_parser().parse_args([
            "corpus", "render",
            "--corpus-dir", str(corpus_dir),
            "--workspace", str(tmp_path),
            "--output", str(out_dir),
        ])
        assert cmd_corpus_render(args) == 0
        for name in RENDER_FILES:
            assert (out_dir / name).is_file(), name

    def test_renders_from_saved_graph(self, tmp_path: Path) -> None:
        graph = _make_graph(tmp_path)
        graph_path = tmp_path / "graph.json"
        graph.save(graph_path)
        out_dir = tmp_path / "indices"
        args = build_parser().parse_args([
            "corpus", "render",
            "--graph-file", str(graph_path),
            "--output", str(out_dir),
        ])
        assert cmd_corpus_render(args) == 0
        assert (out_dir / "gaps.md").read_text(encoding="utf-8") != ""

    def test_missing_corpus_dir_fails(self, tmp_path: Path) -> None:
        args = build_parser().parse_args([
            "corpus", "render",
            "--corpus-dir", str(tmp_path / "no-such-corpus"),
            "--output", str(tmp_path / "indices"),
        ])
        assert cmd_corpus_render(args) == 1

    def test_missing_graph_file_fails(self, tmp_path: Path) -> None:
        args = build_parser().parse_args([
            "corpus", "render",
            "--graph-file", str(tmp_path / "no-such-graph.json"),
            "--output", str(tmp_path / "indices"),
        ])
        assert cmd_corpus_render(args) == 1

    def test_unknown_concept_fails(self, tmp_path: Path) -> None:
        corpus_dir = _make_corpus_dir(tmp_path)
        args = build_parser().parse_args([
            "corpus", "render",
            "--corpus-dir", str(corpus_dir),
            "--workspace", str(tmp_path),
            "--output", str(tmp_path / "indices"),
            "--concept", "nonexistent",
        ])
        assert cmd_corpus_render(args) == 1

    def test_dispatch_table_reaches_render(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        corpus_dir = _make_corpus_dir(tmp_path)
        out_dir = tmp_path / "indices"
        monkeypatch.setattr(sys, "argv", [
            "organvm", "corpus", "render",
            "--corpus-dir", str(corpus_dir),
            "--workspace", str(tmp_path),
            "--output", str(out_dir),
        ])
        assert main() == 0
        assert (out_dir / "concept-index.md").is_file()
