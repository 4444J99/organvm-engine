"""Corpus knowledge graph CLI commands (IRF-SYS-104)."""

import argparse
import json


def cmd_corpus_render(args: argparse.Namespace) -> int:
    """Render the corpus knowledge graph as six markdown indices."""
    from pathlib import Path

    from organvm_engine.corpus.graph import CorpusGraph
    from organvm_engine.corpus.render import RENDER_FILES, render_all
    from organvm_engine.corpus.scanner import scan_corpus

    if args.graph_file:
        graph_path = Path(args.graph_file)
        if not graph_path.is_file():
            print(f"Error: {graph_path} not found")
            return 1
        graph = CorpusGraph.load(graph_path)
    else:
        corpus_dir = Path(args.corpus_dir).resolve()
        ws_root = Path(args.workspace).resolve() if args.workspace else None
        if not corpus_dir.is_dir():
            print(f"Error: {corpus_dir} is not a directory")
            return 1
        graph = scan_corpus(corpus_dir, workspace_root=ws_root)

    try:
        rendered = render_all(graph, concept=args.concept)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in RENDER_FILES:
        (out_dir / name).write_text(rendered[name], encoding="utf-8")

    stats = graph.stats()
    scope = f"concept '{args.concept}'" if args.concept else "full graph"
    print(f"\n  Corpus indices ({scope})")
    print(f"  {'═' * 50}")
    print(f"  Nodes: {stats['total_nodes']}")
    print(f"  Edges: {stats['total_edges']}")
    print(f"\n  Written to {out_dir}:")
    for name in RENDER_FILES:
        print(f"    - {name}")
    return 0


def cmd_corpus_scan(args: argparse.Namespace) -> int:
    """Scan the post-flood corpus and produce a knowledge graph."""
    from pathlib import Path

    from organvm_engine.corpus.scanner import scan_corpus

    corpus_dir = Path(args.corpus_dir).resolve()
    ws_root = Path(args.workspace).resolve() if args.workspace else None

    if not corpus_dir.is_dir():
        print(f"Error: {corpus_dir} is not a directory")
        return 1

    graph = scan_corpus(corpus_dir, workspace_root=ws_root)

    if args.output:
        out_path = Path(args.output)
        graph.save(out_path)
        print(f"Graph saved to {out_path}")

    stats = graph.stats()
    print("\n  Corpus Knowledge Graph")
    print(f"  {'═' * 50}")
    print(f"  Nodes: {stats['total_nodes']}")
    for ntype, count in sorted(stats["node_types"].items()):
        print(f"    {ntype:>12}: {count}")
    print(f"  Edges: {stats['total_edges']}")
    for etype, count in sorted(stats["edge_types"].items()):
        print(f"    {etype:>16}: {count}")

    gaps = graph.concepts_without_implementation()
    if gaps:
        print(f"\n  Unimplemented concepts: {len(gaps)}")
        for g in gaps:
            print(f"    - {g.title}")
    else:
        print(f"\n  All {len(graph.nodes_by_type('concept'))} concepts have implementations.")

    if args.json:
        print(json.dumps(graph.to_dict(), indent=2, ensure_ascii=False))

    return 0


def cmd_corpus_stats(args: argparse.Namespace) -> int:
    """Show statistics for the corpus knowledge graph."""
    from pathlib import Path

    from organvm_engine.corpus.graph import CorpusGraph
    from organvm_engine.corpus.scanner import scan_corpus

    if args.graph_file:
        graph_path = Path(args.graph_file)
        if not graph_path.is_file():
            print(f"Error: {graph_path} not found")
            return 1
        graph = CorpusGraph.load(graph_path)
    else:
        corpus_dir = Path(args.corpus_dir).resolve()
        ws_root = Path(args.workspace).resolve() if args.workspace else None
        graph = scan_corpus(corpus_dir, workspace_root=ws_root)

    stats = graph.stats()

    if args.json:
        print(json.dumps(stats, indent=2))
        return 0

    print("\n  Corpus Knowledge Graph Statistics")
    print(f"  {'═' * 50}")
    print(f"  Total nodes: {stats['total_nodes']}")
    print(f"  Total edges: {stats['total_edges']}")
    print()
    print("  Node types:")
    for ntype, count in sorted(stats["node_types"].items()):
        print(f"    {ntype:>12}: {count}")
    print("  Edge types:")
    for etype, count in sorted(stats["edge_types"].items()):
        print(f"    {etype:>16}: {count}")
    print()
    return 0


def cmd_corpus_gaps(args: argparse.Namespace) -> int:
    """Show concepts without implementation."""
    from pathlib import Path

    from organvm_engine.corpus.graph import CorpusGraph
    from organvm_engine.corpus.scanner import scan_corpus

    if args.graph_file:
        graph = CorpusGraph.load(Path(args.graph_file))
    else:
        corpus_dir = Path(args.corpus_dir).resolve()
        ws_root = Path(args.workspace).resolve() if args.workspace else None
        graph = scan_corpus(corpus_dir, workspace_root=ws_root)

    gaps = graph.concepts_without_implementation()
    concepts = graph.nodes_by_type("concept")

    if args.json:
        print(json.dumps({
            "total_concepts": len(concepts),
            "unimplemented": len(gaps),
            "gaps": [{"uid": g.uid, "title": g.title, **g.metadata} for g in gaps],
        }, indent=2))
        return 0

    print("\n  Implementation Coverage")
    print(f"  {'═' * 50}")
    print(f"  Concepts: {len(concepts)}")
    print(f"  Implemented: {len(concepts) - len(gaps)}")
    print(f"  Gaps: {len(gaps)}")

    if gaps:
        print("\n  Unimplemented:")
        for g in gaps:
            desc = g.metadata.get("description", "")
            print(f"    {g.title}")
            if desc:
                print(f"      {desc[:80]}")
    else:
        print("\n  All concepts have at least one implementation.")

    # Show implementation details for each concept
    if args.verbose:
        print("\n  Implementation Map:")
        for concept in sorted(concepts, key=lambda c: c.uid):
            impls = [e for e in graph.edges_to(concept.uid) if e.edge_type == "IMPLEMENTS"]
            status = f"[{len(impls)} impl]" if impls else "[GAP]"
            print(f"    {status} {concept.title}")
            for impl in impls:
                repo_node = graph.get_node(impl.source)
                aspect = impl.metadata.get("aspect", "")
                name = repo_node.title if repo_node else impl.source
                print(f"           ← {name}: {aspect}")

    return 0


def cmd_corpus_trace(args: argparse.Namespace) -> int:
    """Trace a concept through its full provenance chain."""
    from pathlib import Path

    from organvm_engine.corpus.graph import CorpusGraph
    from organvm_engine.corpus.scanner import scan_corpus

    if args.graph_file:
        graph = CorpusGraph.load(Path(args.graph_file))
    else:
        corpus_dir = Path(args.corpus_dir).resolve()
        ws_root = Path(args.workspace).resolve() if args.workspace else None
        graph = scan_corpus(corpus_dir, workspace_root=ws_root)

    trace = graph.trace_concept(args.concept)

    if args.json:
        print(json.dumps(trace, indent=2, ensure_ascii=False))
        return 0

    if "error" in trace:
        print(f"  Error: {trace['error']}")
        return 1

    print(f"\n  Concept Trace: {trace['title']}")
    print(f"  {'═' * 50}")

    if trace["definitions"]:
        print("\n  Defined by:")
        for d in trace["definitions"]:
            print(f"    [{d['type']}] {d['title']}")

    if trace["documents"]:
        print("\n  Referenced in:")
        for d in trace["documents"]:
            print(f"    [{d['type']}] {d['title']}")

    if trace["implementations"]:
        print(f"\n  Implemented by ({trace['implementation_count']} repos"
              f" across {len(trace['organ_spread'])} organs):")
        for impl in trace["implementations"]:
            organ = f" [{impl['organ']}]" if impl["organ"] else ""
            print(f"    {impl['repo']}{organ}")
            if impl["aspect"]:
                print(f"      {impl['aspect']}")
    else:
        print("\n  [GAP] No implementations found.")

    if trace["organ_spread"]:
        print(f"\n  Organ spread: {', '.join(trace['organ_spread'])}")

    return 0


def cmd_corpus_coverage(args: argparse.Namespace) -> int:
    """Show implementation depth and fragility for all concepts."""
    from pathlib import Path

    from organvm_engine.corpus.graph import CorpusGraph
    from organvm_engine.corpus.scanner import scan_corpus

    if args.graph_file:
        graph = CorpusGraph.load(Path(args.graph_file))
    else:
        corpus_dir = Path(args.corpus_dir).resolve()
        ws_root = Path(args.workspace).resolve() if args.workspace else None
        graph = scan_corpus(corpus_dir, workspace_root=ws_root)

    depth = graph.coverage_depth()

    if args.json:
        print(json.dumps(depth, indent=2, ensure_ascii=False))
        return 0

    fragile = [d for d in depth if d["fragile"]]
    robust = [d for d in depth if not d["fragile"]]

    print("\n  Coverage Depth Report")
    print(f"  {'═' * 50}")
    print(f"  Total concepts: {len(depth)}")
    print(f"  Fragile (≤1 impl): {len(fragile)}")
    print(f"  Robust (≥2 impl): {len(robust)}")

    if fragile:
        print("\n  Fragile concepts:")
        for d in fragile:
            impls = d["implementations"]
            repos = ", ".join(d["repos"]) if d["repos"] else "none"
            tag = "[GAP]" if impls == 0 else "[1 impl]"
            print(f"    {tag} {d['title']} ← {repos}")

    if args.verbose and robust:
        print("\n  Robust concepts:")
        for d in robust:
            spread = f" ({', '.join(d['organs'])})" if d["organs"] else ""
            print(f"    [{d['implementations']} impl] {d['title']}{spread}")

    return 0


def cmd_corpus_repo(args: argparse.Namespace) -> int:
    """Show what concepts a repo implements (reverse lookup)."""
    from pathlib import Path

    from organvm_engine.corpus.graph import CorpusGraph
    from organvm_engine.corpus.scanner import scan_corpus

    if args.graph_file:
        graph = CorpusGraph.load(Path(args.graph_file))
    else:
        corpus_dir = Path(args.corpus_dir).resolve()
        ws_root = Path(args.workspace).resolve() if args.workspace else None
        graph = scan_corpus(corpus_dir, workspace_root=ws_root)

    concepts = graph.repo_concepts(args.repo)

    if args.json:
        print(json.dumps({
            "repo": args.repo,
            "concepts": concepts,
            "count": len(concepts),
        }, indent=2, ensure_ascii=False))
        return 0

    if not concepts:
        print(f"\n  No concepts found for repo '{args.repo}'")
        return 0

    print(f"\n  Concepts implemented by: {args.repo}")
    print(f"  {'═' * 50}")
    for c in concepts:
        print(f"    {c['concept']}")
        if c["aspect"]:
            print(f"      {c['aspect']}")

    print(f"\n  Total: {len(concepts)} concepts")
    return 0
