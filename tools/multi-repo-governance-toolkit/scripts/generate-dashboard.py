#!/usr/bin/env python3
"""Generate a static HTML health dashboard from soak test and metrics data.

Reads all data/soak-test/daily-*.json files plus system-metrics.json and
produces a single self-contained HTML file with inline SVG charts.

Output: data/dashboard/index.html

Usage:
    python3 scripts/generate-dashboard.py
    python3 scripts/generate-dashboard.py --output data/dashboard/index.html
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METRICS_PATH = ROOT / "system-metrics.json"
SOAK_DIR = ROOT / "data" / "soak-test"
DASHBOARD_DIR = ROOT / "data" / "dashboard"

# CMYK palette matching portfolio site
CYAN = "#00AEEF"
MAGENTA = "#EC008C"
YELLOW = "#FFF200"
KEY = "#231F20"
LIGHT_BG = "#F5F5F5"
GREEN = "#2ECC71"
RED = "#E74C3C"
GRAY = "#95A5A6"


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_all_snapshots():
    """Load all soak test snapshots, sorted by date."""
    snapshots = []
    for path in sorted(SOAK_DIR.glob("daily-*.json")):
        data = load_json(path)
        if data:
            data["_path"] = str(path.name)
            snapshots.append(data)
    return snapshots


def svg_bar(values, labels, colors, width=500, bar_height=28, title=""):
    """Generate a horizontal bar chart as SVG."""
    if not values:
        return "<p>No data</p>"

    max_val = max(values) if max(values) > 0 else 1
    padding = 120
    chart_width = width - padding
    height = len(values) * (bar_height + 8) + 40

    lines = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']
    if title:
        lines.append(f'<text x="{width // 2}" y="20" text-anchor="middle" '
                      f'font-family="Jost, sans-serif" font-size="14" fill="{KEY}">{escape(title)}</text>')

    y_offset = 35
    for i, (val, label, color) in enumerate(zip(values, labels, colors)):
        y = y_offset + i * (bar_height + 8)
        bar_w = max(2, int(val / max_val * chart_width))
        lines.append(f'<text x="{padding - 8}" y="{y + bar_height // 2 + 4}" '
                      f'text-anchor="end" font-family="Jost, sans-serif" font-size="12" '
                      f'fill="{KEY}">{escape(str(label))}</text>')
        lines.append(f'<rect x="{padding}" y="{y}" width="{bar_w}" height="{bar_height}" '
                      f'fill="{color}" rx="3"/>')
        lines.append(f'<text x="{padding + bar_w + 6}" y="{y + bar_height // 2 + 4}" '
                      f'font-family="Jost, sans-serif" font-size="12" fill="{KEY}">{val}</text>')

    lines.append("</svg>")
    return "\n".join(lines)


def svg_line_chart(data_points, width=500, height=200, title="", color=CYAN):
    """Generate a line chart as SVG. data_points = [(label, value), ...]"""
    if len(data_points) < 2:
        return f"<p>Need 2+ data points for trend (have {len(data_points)})</p>"

    values = [v for _, v in data_points]
    labels = [l for l, _ in data_points]
    min_v = min(values)
    max_v = max(values)
    v_range = max_v - min_v if max_v != min_v else 1

    padding_l = 50
    padding_r = 20
    padding_t = 30
    padding_b = 40
    chart_w = width - padding_l - padding_r
    chart_h = height - padding_t - padding_b

    points = []
    for i, v in enumerate(values):
        x = padding_l + (i / (len(values) - 1)) * chart_w
        y = padding_t + chart_h - ((v - min_v) / v_range * chart_h)
        points.append((x, y))

    lines = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']
    if title:
        lines.append(f'<text x="{width // 2}" y="18" text-anchor="middle" '
                      f'font-family="Jost, sans-serif" font-size="14" fill="{KEY}">{escape(title)}</text>')

    # Axes
    lines.append(f'<line x1="{padding_l}" y1="{padding_t}" x2="{padding_l}" '
                  f'y2="{padding_t + chart_h}" stroke="{GRAY}" stroke-width="1"/>')
    lines.append(f'<line x1="{padding_l}" y1="{padding_t + chart_h}" '
                  f'x2="{padding_l + chart_w}" y2="{padding_t + chart_h}" '
                  f'stroke="{GRAY}" stroke-width="1"/>')

    # Y-axis labels
    for i in range(5):
        y = padding_t + chart_h - (i / 4 * chart_h)
        v = min_v + (i / 4 * v_range)
        lines.append(f'<text x="{padding_l - 8}" y="{y + 4}" text-anchor="end" '
                      f'font-family="Jost, sans-serif" font-size="10" fill="{GRAY}">'
                      f'{int(v)}</text>')

    # Line
    path_d = " ".join(f"{'M' if i == 0 else 'L'} {x:.1f} {y:.1f}" for i, (x, y) in enumerate(points))
    lines.append(f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="2"/>')

    # Dots
    for x, y in points:
        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')

    # X-axis labels (show first, last, and middle)
    label_indices = [0, len(labels) - 1]
    if len(labels) > 4:
        label_indices.insert(1, len(labels) // 2)
    for i in label_indices:
        x = points[i][0]
        lines.append(f'<text x="{x:.1f}" y="{padding_t + chart_h + 18}" text-anchor="middle" '
                      f'font-family="Jost, sans-serif" font-size="10" fill="{GRAY}">'
                      f'{escape(str(labels[i]))}</text>')

    lines.append("</svg>")
    return "\n".join(lines)


def progress_bar_html(current, total, label="", color=CYAN):
    """Generate a CSS progress bar."""
    pct = min(100, int(current / total * 100)) if total > 0 else 0
    return f"""
    <div style="margin: 12px 0;">
      <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
        <span style="font-size: 14px; color: {KEY};">{escape(label)}</span>
        <span style="font-size: 14px; color: {KEY};">{current}/{total} ({pct}%)</span>
      </div>
      <div style="background: #E0E0E0; border-radius: 6px; height: 24px; overflow: hidden;">
        <div style="background: {color}; width: {pct}%; height: 100%; border-radius: 6px;
                    transition: width 0.5s;"></div>
      </div>
    </div>"""


def status_dot(passing):
    color = GREEN if passing else RED
    label = "PASS" if passing else "FAIL"
    return f'<span style="display: inline-block; width: 12px; height: 12px; ' \
           f'border-radius: 50%; background: {color}; margin-right: 6px;"></span>{label}'


def generate_dashboard(metrics, snapshots):
    """Generate the full HTML dashboard."""
    now = datetime.now(timezone.utc)
    computed = metrics.get("computed", {}) if metrics else {}
    manual = metrics.get("manual", {}) if metrics else {}

    # Separate real vs dry-run snapshots
    real_snaps = [s for s in snapshots if not s.get("dry_run")]
    all_snaps = snapshots

    # VIGILIA timer
    soak_start = datetime(2026, 2, 16, tzinfo=timezone.utc)
    elapsed_days = (now - soak_start).days
    soak_day = min(elapsed_days, 30)
    soak_complete = elapsed_days >= 30
    vigilia_bar = progress_bar_html(soak_day, 30, "VIGILIA (30-Day Soak Test)", MAGENTA)
    vigilia_note = (
        "Soak test ran 2026-02-16 → 2026-03-18. Completed: 30 of 30 days."
        if soak_complete
        else f"Soak test started 2026-02-16. Completes ~2026-03-18. Day {soak_day} of 30."
    )

    # Organ distribution
    per_organ = computed.get("per_organ", {})
    organ_names = []
    organ_counts = []
    organ_colors = [CYAN, MAGENTA, YELLOW, "#2ECC71", "#9B59B6", "#E67E22", "#1ABC9C", "#34495E"]
    for i, (key, data) in enumerate(per_organ.items()):
        organ_names.append(f"{key.replace('ORGAN-', '').replace('META-ORGANVM', 'Meta')}")
        organ_counts.append(data.get("repos", 0))

    organ_chart = svg_bar(
        organ_counts, organ_names,
        [organ_colors[i % len(organ_colors)] for i in range(len(organ_names))],
        width=460, title="Repositories per Organ"
    )

    # Validation trend
    val_data = []
    for s in all_snaps:
        date = s.get("date", "?")
        v = s.get("validation", {})
        passes = 1 if v.get("registry_pass") and v.get("dependency_pass") else 0
        val_data.append((date, passes))

    val_chart = svg_line_chart(val_data, title="Validation Status (1=pass, 0=fail)",
                               color=GREEN) if len(val_data) >= 2 else "<p>Trend available after 2+ snapshots</p>"

    # CI trend
    ci_data = [(s.get("date", "?"), s.get("ci", {}).get("passing", 0)) for s in real_snaps]
    ci_chart = svg_line_chart(ci_data, title="CI Passing Repos", color=CYAN) if len(ci_data) >= 2 else \
        "<p>CI trend available after 2+ real data points</p>"

    # Engagement trend
    eng_data = [(s.get("date", "?"), s.get("engagement", {}).get("total_stars", 0)) for s in real_snaps]
    eng_chart = svg_line_chart(eng_data, title="Total Stars", color=YELLOW) if len(eng_data) >= 2 else \
        "<p>Engagement trend available after 2+ real data points</p>"

    # Latest validation status
    latest = all_snaps[-1] if all_snaps else {}
    latest_val = latest.get("validation", {})
    reg_status = status_dot(latest_val.get("registry_pass", False))
    dep_status = status_dot(latest_val.get("dependency_pass", False))

    # Resolve optional metric values (prefer computed, fall back gracefully)
    wc = computed.get("word_counts") or {}
    _tw = wc.get("total") if wc.get("total") is not None else manual.get("total_words")
    words_display = f"{int(_tw):,}" if isinstance(_tw, (int, float)) else "n/a"
    code_files = manual.get("code_files") if manual.get("code_files") not in (None, "", "?") else "n/a"
    test_files = manual.get("test_files") if manual.get("test_files") not in (None, "", "?") else "n/a"
    organs_display = f"{computed.get('operational_organs', '?')}/{computed.get('total_organs', '?')}"

    # System numbers
    stats_html = f"""
    <div class="stat-grid">
      <div class="stat"><div class="stat-num">{computed.get('total_repos', '?')}</div><div class="stat-label">Total Repos</div></div>
      <div class="stat"><div class="stat-num">{computed.get('active_repos', '?')}</div><div class="stat-label">Active</div></div>
      <div class="stat"><div class="stat-num">{computed.get('published_essays', '?')}</div><div class="stat-label">Essays</div></div>
      <div class="stat"><div class="stat-num">{computed.get('sprints_completed', '?')}</div><div class="stat-label">Sprints</div></div>
      <div class="stat"><div class="stat-num">{code_files}</div><div class="stat-label">Code Files</div></div>
      <div class="stat"><div class="stat-num">{test_files}</div><div class="stat-label">Test Files</div></div>
      <div class="stat"><div class="stat-num">{words_display}</div><div class="stat-label">Words</div></div>
      <div class="stat"><div class="stat-num">{organs_display}</div><div class="stat-label">Organs</div></div>
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ORGANVM System Health Dashboard</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Jost:wght@300;400;500;600&display=swap');

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Jost', sans-serif;
    background: {LIGHT_BG};
    color: {KEY};
    padding: 24px;
    max-width: 1100px;
    margin: 0 auto;
  }}
  h1 {{
    font-weight: 300;
    font-size: 28px;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 4px;
  }}
  h1 span {{ color: {CYAN}; }}
  .subtitle {{
    font-size: 13px;
    color: {GRAY};
    margin-bottom: 24px;
  }}
  .card {{
    background: white;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .card h2 {{
    font-size: 16px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 2px solid {CYAN};
  }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 768px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  .stat-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
  }}
  @media (max-width: 600px) {{ .stat-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
  .stat {{
    text-align: center;
    padding: 12px 8px;
    background: {LIGHT_BG};
    border-radius: 6px;
  }}
  .stat-num {{
    font-size: 24px;
    font-weight: 600;
    color: {CYAN};
  }}
  .stat-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: {GRAY};
    margin-top: 4px;
  }}
  .status-row {{
    display: flex;
    align-items: center;
    padding: 8px 0;
    font-size: 14px;
  }}
  .footer {{
    text-align: center;
    font-size: 12px;
    color: {GRAY};
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid #E0E0E0;
  }}
</style>
</head>
<body>

<h1><span>ORGANVM</span> System Health</h1>
<p class="subtitle">Generated {now.strftime('%Y-%m-%d %H:%M UTC')} &middot;
  {len(all_snaps)} snapshot(s), {len(real_snaps)} real data point(s)</p>

<!-- VIGILIA Timer -->
<div class="card">
  <h2>VIGILIA Timer</h2>
  {vigilia_bar}
  <p style="font-size: 13px; color: {GRAY}; margin-top: 8px;">
    {vigilia_note}
  </p>
</div>

<!-- System Numbers -->
<div class="card">
  <h2>System Overview</h2>
  {stats_html}
</div>

<!-- Health Status -->
<div class="grid">
  <div class="card">
    <h2>Validation Status</h2>
    <div class="status-row">{reg_status} &nbsp; Registry Integrity</div>
    <div class="status-row">{dep_status} &nbsp; Dependency Graph</div>
    <div style="margin-top: 12px;">
      {val_chart}
    </div>
  </div>

  <div class="card">
    <h2>Repository Distribution</h2>
    {organ_chart}
  </div>
</div>

<!-- Trends -->
<div class="grid">
  <div class="card">
    <h2>CI Stability</h2>
    {ci_chart}
  </div>

  <div class="card">
    <h2>Engagement</h2>
    {eng_chart}
  </div>
</div>

<div class="footer">
  ORGANVM Health Dashboard &middot; Sprint 33 OPERATIO &middot;
  Data from soak-test-daily.yml + system-metrics.json
</div>

</body>
</html>"""

    return html


def main():
    parser = argparse.ArgumentParser(description="Generate static HTML health dashboard")
    parser.add_argument("--output", type=Path, help="Output file path")
    args = parser.parse_args()

    print("Dashboard Generator")
    print("=" * 40)

    metrics = load_json(METRICS_PATH)
    if not metrics:
        print("WARNING: Could not load system-metrics.json")

    snapshots = load_all_snapshots()
    print(f"Loaded {len(snapshots)} soak test snapshot(s)")

    html = generate_dashboard(metrics, snapshots)

    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    output_path = args.output or (DASHBOARD_DIR / "index.html")
    output_path.write_text(html, encoding="utf-8")

    print(f"Dashboard written: {output_path}")
    print(f"Size: {len(html):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
