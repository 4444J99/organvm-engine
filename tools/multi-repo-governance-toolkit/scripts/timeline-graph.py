#!/usr/bin/env python3
"""
timeline-graph.py — Build and view the timeline-rooted prompt graph.

The architecture (per user 2026-05-05):

    TIMELINE (root, chronological τ-axis)
      └─ PROMPT (inception event at τ=0)
           └─ ATOMIC UNIT (σ=1 decomposition)
                 ├─→ PRAXIS branches (multi-directional possibilities, alternative realizations)
                 ├─→ PRAGMA pointers (current implementation — file references, commits)
                 └─→ TELOS pointer (ideal form — target end-state)

This script:
  - build  → assembles the timeline-graph from data/atoms/*.jsonl into one JSONL
  - view   → renders any prompt's full graph as readable markdown

Run from the corpus root (where data/atoms/ lives).
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def load_jsonl(path):
    items = []
    with open(path) as f:
        for line in f:
            try:
                items.append(json.loads(line))
            except Exception:
                pass
    return items


def build(out_path: Path):
    """Assemble timeline-graph.jsonl from Pipeline B sources."""
    print("Loading Pipeline B sources...")
    annotated_prompts = load_jsonl('data/atoms/annotated-prompts.jsonl')
    atomized_tasks = load_jsonl('data/atoms/atomized-tasks.jsonl')
    atom_links = load_jsonl('data/atoms/atom-links.jsonl')
    ideal_forms = load_jsonl('data/atoms/ideal-forms.jsonl')

    print(f"  Annotated prompts:  {len(annotated_prompts):>6,}")
    print(f"  Atomized tasks:     {len(atomized_tasks):>6,}")
    print(f"  Atom-links:         {len(atom_links):>6,}")
    print(f"  Ideal forms:        {len(ideal_forms):>6,}")

    task_by_id = {t['id']: t for t in atomized_tasks}
    links_by_prompt = defaultdict(list)
    for link in atom_links:
        pid = link.get('prompt_id')
        if pid:
            links_by_prompt[pid].append(link)

    # Pre-compute form keyword sets for telos matching
    form_keywords = []
    for f in ideal_forms:
        label = f.get('label', '')
        words = set(w.lower() for w in label.replace('/', ' ').replace('+', ' ').split() if len(w) > 3)
        form_keywords.append((f, words))

    records = []
    for p in annotated_prompts:
        pid = p.get('id')
        ts = (p.get('source') or {}).get('timestamp')
        if not ts:
            continue

        task_records = []
        for link in links_by_prompt.get(pid, []):
            tid = link.get('task_id')
            task = task_by_id.get(tid, {})

            # Telos: best-overlap ideal-form match
            task_tag_set = set(task.get('tags', []))
            best_form, best_overlap = None, 0
            if task_tag_set:
                for f, kw in form_keywords:
                    overlap = len(task_tag_set & kw)
                    if overlap > best_overlap:
                        best_overlap, best_form = overlap, f
            telos = None
            if best_form and best_overlap >= 1:
                mat = best_form.get('materialization', {})
                telos = {
                    'form_id': best_form['form_id'],
                    'label': best_form['label'],
                    'completeness': best_form.get('completeness'),
                    'verified_done': mat.get('verified_done'),
                    'answered': mat.get('answered'),
                    'total': mat.get('total'),
                }

            task_records.append({
                'task_id': tid,
                'title': (task.get('title') or '')[:120],
                'status': task.get('status'),
                'actionable': task.get('actionable'),
                'tags': task.get('tags', [])[:5],
                'task_type': task.get('task_type'),
                'project_organ': (task.get('project') or {}).get('organ'),
                'project_repo': (task.get('project') or {}).get('repo'),
                # Three gravitational pillars:
                'praxis_branches': [],   # data-layer addition needed
                'pragma_pointers': {     # current implementation
                    'shared_refs': link.get('shared_refs', [])[:5],
                    'shared_tags': link.get('shared_tags', [])[:5],
                    'jaccard': link.get('jaccard'),
                },
                'telos_pointer': telos,  # ideal form
            })

        records.append({
            'timestamp': ts,
            'prompt_id': pid,
            'session_id': (p.get('source') or {}).get('session_id'),
            'thread_id': (p.get('threading') or {}).get('thread_id'),
            'thread_label': (p.get('threading') or {}).get('thread_label'),
            'agent': (p.get('source') or {}).get('agent'),
            'prompt_text': (p.get('content') or {}).get('text', '')[:300],
            'prompt_type': (p.get('classification') or {}).get('prompt_type'),
            'linked_task_count': len(task_records),
            'linked_tasks': task_records,
        })

    records.sort(key=lambda r: r['timestamp'])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        for r in records:
            f.write(json.dumps(r, default=str) + '\n')

    total_tasks = sum(r['linked_task_count'] for r in records)
    with_telos = sum(1 for r in records for t in r['linked_tasks'] if t['telos_pointer'])
    with_pragma = sum(1 for r in records for t in r['linked_tasks'] if t['pragma_pointers']['shared_refs'])

    print(f"\n  Records:                {len(records):>6,}")
    print(f"  Linked tasks:           {total_tasks:>6,}")
    print(f"  With pragma file refs:  {with_pragma:>6,}")
    print(f"  With telos pointer:     {with_telos:>6,}")
    print(f"  Wrote:                  {out_path}")


def view(graph_path: Path, prompt_id: str = None, since: str = None, limit: int = 20):
    """Render graph entries as markdown."""
    if not graph_path.exists():
        print(f"Graph not found at {graph_path}. Run `build` first.", file=sys.stderr)
        sys.exit(1)

    records = load_jsonl(graph_path)

    # Filter
    if prompt_id:
        matches = [r for r in records if r.get('prompt_id', '').startswith(prompt_id)]
        if not matches:
            print(f"No prompt found matching id prefix: {prompt_id}", file=sys.stderr)
            sys.exit(1)
        records = matches
    elif since:
        records = [r for r in records if r['timestamp'] >= since]
        # Show newest first when filtering by date
        records.sort(key=lambda r: r['timestamp'], reverse=True)
        records = records[:limit]
    else:
        # Default: most recent N prompts with at least one linked task
        records = [r for r in records if r['linked_task_count'] > 0]
        records.sort(key=lambda r: r['timestamp'], reverse=True)
        records = records[:limit]

    for r in records:
        print(f"## {r['timestamp']} — `{r['prompt_id']}`")
        print()
        print(f"- **agent**: {r.get('agent', '?')} | **session**: `{r.get('session_id', '?')}` | **thread**: `{r.get('thread_label', '?')}`")
        print(f"- **prompt-type**: {r.get('prompt_type', '?')} | **linked-task-count**: {r['linked_task_count']}")
        print()
        print("### Inception (the prompt)")
        print()
        text = r.get('prompt_text', '')
        for line in text.splitlines()[:6]:
            print(f"> {line}")
        if len(text.splitlines()) > 6:
            print(f"> *... ({len(text)} chars total)*")
        print()

        if r['linked_tasks']:
            print(f"### Atomic units ({r['linked_task_count']})")
            print()
            for task in r['linked_tasks']:
                print(f"#### `{task['task_id']}` — {task['title']}")
                print(f"- **status**: {task.get('status', '?')} | **type**: {task.get('task_type', '?')} | **organ**: {task.get('project_organ', '?')} | **repo**: {task.get('project_repo', '?')}")
                tags = ', '.join(task.get('tags', []))
                if tags:
                    print(f"- **tags**: {tags}")
                print()
                # Three gravitational pillars
                pragma = task.get('pragma_pointers', {})
                if pragma.get('shared_refs') or pragma.get('shared_tags'):
                    print("  **PRAGMA** (current implementation)")
                    if pragma.get('shared_refs'):
                        for ref in pragma['shared_refs']:
                            print(f"  - file: `{ref}`")
                    if pragma.get('shared_tags'):
                        print(f"  - shared-tags: {', '.join(pragma['shared_tags'])}")
                    if pragma.get('jaccard'):
                        print(f"  - jaccard-similarity: {pragma['jaccard']:.3f}")
                    print()

                telos = task.get('telos_pointer')
                if telos:
                    print("  **TELOS** (ideal form)")
                    print(f"  - form-id: `{telos['form_id']}`")
                    print(f"  - label: {telos['label']}")
                    if telos.get('completeness') is not None:
                        print(f"  - completeness: {telos['completeness']:.2f}")
                    if telos.get('total'):
                        print(f"  - materialization: {telos.get('verified_done', 0)} verified-done / {telos.get('answered', 0)} answered / {telos['total']} total")
                    print()

                praxis = task.get('praxis_branches', [])
                if praxis:
                    print("  **PRAXIS** (alternative branches)")
                    for branch in praxis:
                        print(f"  - {branch}")
                    print()
                else:
                    print("  **PRAXIS**: *(no alternative branches recorded — data-layer field needs adding)*")
                    print()
        print("---")
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_build = sub.add_parser('build', help='Assemble timeline-graph.jsonl from Pipeline B')
    p_build.add_argument('--out', default='data/prompt-registry/timeline-graph.jsonl', help='Output JSONL path')

    p_view = sub.add_parser('view', help='Render graph as markdown')
    p_view.add_argument('--graph', default='data/prompt-registry/timeline-graph.jsonl', help='Input JSONL path')
    p_view.add_argument('--prompt-id', help='Show specific prompt (prefix match)')
    p_view.add_argument('--since', help='Show prompts since YYYY-MM-DD (newest first)')
    p_view.add_argument('--limit', type=int, default=20, help='Max records to render (default: 20)')

    args = ap.parse_args()

    if args.cmd == 'build':
        build(Path(args.out))
    elif args.cmd == 'view':
        view(Path(args.graph), prompt_id=args.prompt_id, since=args.since, limit=args.limit)


if __name__ == '__main__':
    main()
