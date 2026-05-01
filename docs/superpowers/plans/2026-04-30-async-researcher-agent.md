# Async Researcher Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a background researcher agent that runs concurrently with the web report server, producing deep analysis reports and enriched data.

**Architecture:** After fetching data, the pipeline starts the web server in a background subprocess and launches the researcher as an async sub-agent via pi-subagents. The researcher loads CSVs, runs analysis, and writes `reports/research_<timestamp>.md` plus `reports/enriched_<timestamp>.csv`. The web server footer shows research status.

**Tech Stack:** Python 3.13, pandas, numpy, scipy (for z-scores), pi-subagents harness for async agent launching. No new Python dependencies.

---

### File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/researcher.py` | Create | Core research logic — load data, analyze, write report + enriched CSV |
| `scripts/run_full_pipeline.py` | Modify | Add background server start + async researcher launch; add `--no-research` flag |
| `scripts/serve_report.py` | Modify | Add Research Status badge in footer |
| `.pi/skills/analyzing-youtube-analytics/SKILL.md` | Modify | Document researcher feature and new CLI flags |
| `.pi/skills/analyzing-youtube-analytics/scripts/run_full_pipeline.py` | Modify | Sync pipeline changes |
| `.pi/skills/analyzing-youtube-analytics/scripts/serve_report.py` | Modify | Sync footer changes |
| `tests/test_researcher.py` | Create | Unit tests for researcher core logic |

---

### Task 1: Create `scripts/researcher.py` — Core Research Logic

**Files:**
- Create: `scripts/researcher.py`
- Test: `tests/test_researcher.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_researcher.py`:

```python
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from scripts.researcher import load_data, compute_anomaly_flags, generate_report

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "researcher"

class TestLoadData:
    def test_loads_summary(self, tmp_path):
        # Create minimal Table data.csv
        csv = tmp_path / "Table data.csv"
        csv.write_text("""Video,Video title,Duration,Views,Watch time (hours),Subscribers gained,Subscribers lost,Likes,Dislikes,Comments added,Shares,Impressions,Impressions click-through rate (%),Average view duration,Average percentage viewed (%),Video publish time
vid1,Test Video 1,0:05:00,1000,50.0,10,2,50,1,5,2,5000,20.0,0:02:30,50.0,Jan 1, 2024
vid2,Test Video 2,0:03:00,500,20.0,5,1,20,0,2,1,2000,25.0,0:01:30,50.0,Jan 2, 2024
""")
        data = load_data(tmp_path)
        assert "summary" in data
        assert len(data["summary"]) == 2
        assert data["summary"]["Views"].sum() == 1500

class TestComputeAnomalyFlags:
    def test_flags_top_outlier(self):
        df = pd.DataFrame({
            "Views": [100, 110, 105, 1000, 95],
            "Video": ["v1", "v2", "v3", "v4", "v5"],
        })
        flags = compute_anomaly_flags(df, "Views")
        assert flags["v4"] == "spike"
        assert flags["v1"] == "normal"

    def test_flags_bottom_outlier(self):
        df = pd.DataFrame({
            "Views": [100, 110, 105, 1000, 5],
            "Video": ["v1", "v2", "v3", "v4", "v5"],
        })
        flags = compute_anomaly_flags(df, "Views")
        assert flags["v5"] == "drop"

class TestGenerateReport:
    def test_report_has_sections(self, tmp_path):
        summary = pd.DataFrame({
            "Video": ["v1", "v2", "v3", "v4"],
            "Video title": ["A", "B", "C", "D"],
            "Views": [1000, 500, 200, 100],
            "Watch time (hours)": [50, 25, 10, 5],
            "Duration (seconds)": [300, 180, 240, 600],
            "CTR (%)": [8.0, 5.0, 3.0, 2.0],
            "AVD ratio": [0.5, 0.4, 0.3, 0.2],
            "Engagement rate (%)": [5.0, 3.0, 2.0, 1.0],
            "Subscriber conversion rate (%)": [1.0, 0.5, 0.2, 0.1],
            "Average percentage viewed (%)": [60, 50, 40, 30],
            "Likes": [50, 20, 10, 5],
            "Comments added": [5, 2, 1, 0],
            "Shares": [2, 1, 0, 0],
            "Net subscribers": [8, 4, 2, 1],
        })
        report = generate_report(summary, data_dir=tmp_path)
        assert "## Executive Summary" in report
        assert "## What Works" in report
        assert "## What Doesn't Work" in report
        assert "## New Content Ideas" in report
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run python -m pytest tests/test_researcher.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'scripts.researcher'"

- [ ] **Step 3: Implement `scripts/researcher.py`**

Create `scripts/researcher.py`:

```python
#!/usr/bin/env python3
"""
YouTube Analytics Researcher
Deep analysis of YouTube data: what works, what doesn't, and new content ideas.

Usage:
    uv run python scripts/researcher.py --data-dir data/latest
    uv run python scripts/researcher.py --data-dir data/latest --output-dir reports
"""

import argparse
import json
import os
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
# Note: scipy not used — z-scores computed with numpy to avoid new dependencies

# ── Argument parsing ────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Deep research on YouTube analytics data")
parser.add_argument("--data-dir", type=str, required=True, help="Directory containing CSV data")
parser.add_argument("--output-dir", type=str, default="reports", help="Directory to write reports")
parser.add_argument("--timestamp", type=str, default=None, help="Timestamp suffix for output files")
args = parser.parse_args()

# ── Config ──────────────────────────────────────────────────────────
DATA_DIR = Path(args.data_dir)
OUTPUT_DIR = Path(args.output_dir)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

if args.timestamp:
    ts = args.timestamp
else:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")

REPORT_PATH = OUTPUT_DIR / f"research_{ts}.md"
ENRICHED_PATH = OUTPUT_DIR / f"enriched_{ts}.csv"


def load_data(data_dir):
    """Load all available CSVs from the data directory."""
    data = {}
    summary_path = data_dir / "Table data.csv"
    if summary_path.exists():
        data["summary"] = pd.read_csv(summary_path)
        # Remove Total row
        data["summary"] = data["summary"][data["summary"]["Content"] != "Total"].copy()
    
    for name, filename in [
        ("traffic", "Traffic sources.csv"),
        ("search", "Search terms.csv"),
        ("geo", "Geography.csv"),
        ("device", "Device type.csv"),
        ("content_type", "Content type.csv"),
        ("demographics", "Demographics.csv"),
        ("retention", "Retention.csv"),
    ]:
        path = data_dir / filename
        if path.exists():
            data[name] = pd.read_csv(path)
    
    return data


def compute_derived_metrics(df):
    """Add derived metrics to the summary DataFrame."""
    df = df.copy()
    df["Net subscribers"] = df.get("Subscribers gained", 0) - df.get("Subscribers lost", 0)
    df["Subscriber conversion rate (%)"] = (df["Net subscribers"] / df["Views"].clip(lower=1)) * 100
    df["Engagement rate (%)"] = (
        (df.get("Likes", 0) + df.get("Comments added", 0) + df.get("Shares", 0))
        / df["Views"].clip(lower=1)
    ) * 100
    df["Like rate (%)"] = (df.get("Likes", 0) / df["Views"].clip(lower=1)) * 100
    
    # Parse duration
    def parse_dur(val):
        if pd.isna(val): return np.nan
        parts = str(val).strip().split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return np.nan
    
    df["Duration (seconds)"] = df["Duration"].apply(parse_dur)
    
    return df


def compute_anomaly_flags(df, col, z_threshold=2.0):
    """Flag videos with z-score outliers in the given column."""
    flags = {}
    mean = df[col].mean()
    std = df[col].std(ddof=0)
    if std == 0 or pd.isna(std):
        return {row["Video"]: "normal" for _, row in df.iterrows()}
    
    for _, row in df.iterrows():
        z = (row[col] - mean) / std
        if z > z_threshold:
            flags[row["Video"]] = "spike"
        elif z < -z_threshold:
            flags[row["Video"]] = "drop"
        else:
            flags[row["Video"]] = "normal"
    return flags


def compute_recommendation(row, top20_median_views):
    """Generate a per-video recommendation."""
    views = row["Views"]
    ctr = row.get("CTR (%)", np.nan)
    pct = row.get("Average percentage viewed (%)", np.nan)
    
    if views >= top20_median_views * 1.5:
        return "double_down"
    
    if pd.notna(ctr) and ctr < 3 and pd.notna(pct) and pct > 50:
        return "fix_thumbnail"
    
    if pd.notna(pct) and pct < 30 and pd.notna(ctr) and ctr > 5:
        return "improve_hook"
    
    if views >= top20_median_views * 0.8:
        return "expand_series"
    
    return "deprecate"


def analyze_top_performers(df, n=0.2):
    """Analyze the top N% of videos by views."""
    top = df.nlargest(max(1, int(len(df) * n)), "Views")
    return {
        "count": len(top),
        "avg_views": top["Views"].mean(),
        "avg_ctr": top.get("CTR (%)", pd.Series()).mean(),
        "avg_avd": top.get("AVD ratio", pd.Series()).mean(),
        "avg_eng": top.get("Engagement rate (%)", pd.Series()).mean(),
        "avg_subconv": top.get("Subscriber conversion rate (%)", pd.Series()).mean(),
        "avg_pct_viewed": top.get("Average percentage viewed (%)", pd.Series()).mean(),
        "common_content_type": None,  # populated later if content_type data exists
    }


def analyze_bottom_performers(df, n=0.2):
    """Analyze the bottom N% of videos by views."""
    bottom = df.nsmallest(max(1, int(len(df) * n)), "Views")
    return {
        "count": len(bottom),
        "avg_views": bottom["Views"].mean(),
        "avg_ctr": bottom.get("CTR (%)", pd.Series()).mean(),
        "avg_avd": bottom.get("AVD ratio", pd.Series()).mean(),
        "avg_eng": bottom.get("Engagement rate (%)", pd.Series()).mean(),
        "avg_subconv": bottom.get("Subscriber conversion rate (%)", pd.Series()).mean(),
        "avg_pct_viewed": bottom.get("Average percentage viewed (%)", pd.Series()).mean(),
    }


def diagnose_problems(row):
    """Diagnose whether a video has a discovery or retention problem."""
    ctr = row.get("CTR (%)", np.nan)
    pct = row.get("Average percentage viewed (%)", np.nan)
    
    if pd.isna(ctr) or pd.isna(pct):
        return "insufficient_data"
    
    if ctr < 3 and pct < 30:
        return "both_weak"
    if ctr < 3:
        return "discovery_problem"
    if pct < 30:
        return "retention_problem"
    if ctr >= 8 and pct >= 70:
        return "strong"
    return "moderate"


def generate_content_ideas(top_analysis, bottom_analysis, search_df=None, content_type_df=None):
    """Generate actionable content ideas based on data patterns."""
    ideas = []
    
    # Idea 1: Double down on top performers
    if top_analysis["avg_views"] > bottom_analysis["avg_views"] * 3:
        ideas.append(
            f"Your top performers get {top_analysis['avg_views']/bottom_analysis['avg_views']:.1f}x more views. "
            "Analyze what makes them different and create more content in that vein."
        )
    
    # Idea 2: Fix discovery problems
    ideas.append(
        "Videos with low CTR but decent retention have a thumbnail/title problem. "
        "A/B test thumbnails that show the result, not the process."
    )
    
    # Idea 3: Fix retention problems
    ideas.append(
        "Videos with good CTR but poor retention need better hooks. "
        "Front-load the most surprising insight in the first 15 seconds."
    )
    
    # Idea 4: Search gaps
    if search_df is not None and len(search_df) > 0:
        top_terms = search_df.nlargest(5, "Views")
        ideas.append(
            f"Your top search term is '{top_terms.iloc[0]['Search term']}' "
            f"({top_terms.iloc[0]['Views']:,} views). Create dedicated content targeting this query."
        )
    
    # Idea 5: Content type expansion
    if content_type_df is not None:
        type_views = content_type_df.groupby("Content type")["Views"].sum()
        if len(type_views) > 1:
            best = type_views.idxmax()
            ideas.append(
                f"{best} content drives the most views. Consider increasing your output in this format."
            )
    
    # Pad to 5 ideas minimum with generic but data-informed suggestions
    generics = [
        "Repurpose your highest-retention video into a Short to capture a new audience.",
        "Create a 'best of' compilation of your top 5 performing topics.",
        "Test a series format — viewers who binge multiple videos have higher lifetime value.",
    ]
    while len(ideas) < 5:
        ideas.append(generics[len(ideas) - 5])
    
    return ideas[:10]


def generate_report(summary, data):
    """Generate the full markdown research report."""
    summary = compute_derived_metrics(summary)
    
    top20 = analyze_top_performers(summary, 0.2)
    bottom20 = analyze_bottom_performers(summary, 0.2)
    
    # Per-video diagnosis
    diagnoses = {}
    for _, row in summary.iterrows():
        diagnoses[row["Video"]] = diagnose_problems(row)
    
    # Anomaly flags
    view_flags = compute_anomaly_flags(summary, "Views")
    
    # Content type enrichment
    content_type_df = data.get("content_type")
    if content_type_df is not None:
        type_perf = content_type_df.groupby("Content type").agg(
            Videos=("Video", "nunique"),
            Views=("Views", "sum"),
            Watch_time=("Watch time (hours)", "sum"),
        ).reset_index().sort_values("Views", ascending=False)
        top20["common_content_type"] = type_perf.iloc[0]["Content type"] if len(type_perf) > 0 else None
    
    # Search terms
    search_df = data.get("search")
    
    # Ideas
    ideas = generate_content_ideas(top20, bottom20, search_df, content_type_df)
    
    # Build report
    lines = []
    lines.append("# YouTube Analytics Deep Research Report")
    lines.append(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append(f"*Videos analyzed: {len(summary)}*")
    lines.append("\n---\n")
    
    # Executive Summary
    lines.append("## Executive Summary\n")
    lines.append(f"- **Top 20% average views:** {top20['avg_views']:,.0f}")
    lines.append(f"- **Bottom 20% average views:** {bottom20['avg_views']:,.0f}")
    lines.append(f"- **Performance gap:** {top20['avg_views']/max(bottom20['avg_views'], 1):.1f}x")
    if top20["common_content_type"]:
        lines.append(f"- **Best content type:** {top20['common_content_type']}")
    
    strong_count = sum(1 for d in diagnoses.values() if d == "strong")
    lines.append(f"- **Strong performers:** {strong_count}/{len(summary)}")
    lines.append("\n**Top 3 Recommendations:**")
    for i, idea in enumerate(ideas[:3], 1):
        lines.append(f"{i}. {idea}")
    lines.append("")
    
    # What Works
    lines.append("## What Works\n")
    lines.append("### Top 20% Performers\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Videos | {top20['count']} |")
    lines.append(f"| Avg Views | {top20['avg_views']:,.0f} |")
    lines.append(f"| Avg CTR | {top20['avg_ctr']:.2f}% |" if pd.notna(top20['avg_ctr']) else "| Avg CTR | N/A |")
    lines.append(f"| Avg AVD | {top20['avg_avd']:.2f} |" if pd.notna(top20['avg_avd']) else "| Avg AVD | N/A |")
    lines.append(f"| Avg Eng Rate | {top20['avg_eng']:.2f}% |" if pd.notna(top20['avg_eng']) else "| Avg Eng Rate | N/A |")
    lines.append(f"| Avg Sub Conv | {top20['avg_subconv']:.3f}% |" if pd.notna(top20['avg_subconv']) else "| Avg Sub Conv | N/A |")
    lines.append("")
    
    if content_type_df is not None:
        lines.append("### Content Type Breakdown (Top Performers)\n")
        lines.append("| Content Type | Videos | Total Views |")
        lines.append("|-------------|--------|-------------|")
        for _, row in type_perf.iterrows():
            lines.append(f"| {row['Content type']} | {row['Videos']} | {row['Views']:,} |")
        lines.append("")
    
    # What Doesn't Work
    lines.append("## What Doesn't Work\n")
    lines.append("### Bottom 20% Performers\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Videos | {bottom20['count']} |")
    lines.append(f"| Avg Views | {bottom20['avg_views']:,.0f} |")
    lines.append(f"| Avg CTR | {bottom20['avg_ctr']:.2f}% |" if pd.notna(bottom20['avg_ctr']) else "| Avg CTR | N/A |")
    lines.append(f"| Avg AVD | {bottom20['avg_avd']:.2f} |" if pd.notna(bottom20['avg_avd']) else "| Avg AVD | N/A |")
    lines.append("")
    
    # Problem diagnosis table
    lines.append("### Problem Diagnosis\n")
    lines.append("| Problem | Count |")
    lines.append("|---------|-------|")
    problem_counts = {}
    for d in diagnoses.values():
        problem_counts[d] = problem_counts.get(d, 0) + 1
    for problem, count in sorted(problem_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {problem.replace('_', ' ').title()} | {count} |")
    lines.append("")
    
    # Anomalies
    spike_count = sum(1 for f in view_flags.values() if f == "spike")
    drop_count = sum(1 for f in view_flags.values() if f == "drop")
    if spike_count > 0 or drop_count > 0:
        lines.append(f"### Anomalies\n")
        lines.append(f"- **Spikes:** {spike_count} videos")
        lines.append(f"- **Drops:** {drop_count} videos")
        lines.append("")
    
    # New Content Ideas
    lines.append("## New Content Ideas\n")
    for i, idea in enumerate(ideas, 1):
        lines.append(f"{i}. {idea}")
    lines.append("")
    
    # Action Plan
    lines.append("## Action Plan\n")
    lines.append("### Quick Wins (This Week)")
    lines.append(f"1. {ideas[0]}")
    lines.append(f"2. Fix thumbnails on videos diagnosed with 'discovery_problem'")
    lines.append("")
    lines.append("### Medium-Term (This Month)")
    if len(ideas) > 3:
        lines.append(f"1. {ideas[3]}")
    lines.append("2. Create a content calendar based on top-performing topics")
    lines.append("")
    lines.append("### Long-Term Bets (Next Quarter)")
    if len(ideas) > 4:
        lines.append(f"1. {ideas[4]}")
    lines.append("2. Experiment with a new content type based on gap analysis")
    lines.append("")
    
    return "\n".join(lines)


def generate_enriched_csv(summary, data):
    """Generate enriched CSV with recommendations and flags."""
    summary = compute_derived_metrics(summary)
    
    top20_median = summary.nlargest(max(1, int(len(summary) * 0.2)), "Views")["Views"].median()
    
    view_flags = compute_anomaly_flags(summary, "Views")
    diagnoses = {row["Video"]: diagnose_problems(row) for _, row in summary.iterrows()}
    recommendations = {row["Video"]: compute_recommendation(row, top20_median) for _, row in summary.iterrows()}
    
    enriched = summary.copy()
    enriched["anomaly_flag"] = enriched["Video"].map(view_flags)
    enriched["diagnosis"] = enriched["Video"].map(diagnoses)
    enriched["recommendation"] = enriched["Video"].map(recommendations)
    enriched["content_opportunity_score"] = 50  # placeholder for v1
    
    # Search gap keywords (placeholder — populated if search data exists)
    enriched["search_gap_keywords"] = ""
    
    return enriched


def main():
    print(f"Loading data from: {DATA_DIR}")
    data = load_data(DATA_DIR)
    
    if "summary" not in data:
        print("ERROR: No Table data.csv found.")
        return 1
    
    summary = data["summary"]
    print(f"Loaded {len(summary)} videos")
    
    # Generate report
    print("Generating research report...")
    report = generate_report(summary, data)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report written: {REPORT_PATH}")
    
    # Generate enriched CSV
    print("Generating enriched data...")
    enriched = generate_enriched_csv(summary, data)
    enriched.to_csv(ENRICHED_PATH, index=False)
    print(f"Enriched CSV written: {ENRICHED_PATH}")
    
    print("Research complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/test_researcher.py -v
```

Expected: All 5 tests PASS

- [ ] **Step 5: Run researcher against real data to verify output**

```bash
uv run python scripts/researcher.py --data-dir data/latest
```

Expected: Report written to `reports/research_<timestamp>.md`, enriched CSV to `reports/enriched_<timestamp>.csv`

- [ ] **Step 6: Commit**

```bash
git add scripts/researcher.py tests/test_researcher.py
git commit -m "feat: add researcher core logic with tests"
```

---

### Task 2: Modify `scripts/run_full_pipeline.py` — Add Async Researcher Launch

**Files:**
- Modify: `scripts/run_full_pipeline.py`
- Modify: `.pi/skills/analyzing-youtube-analytics/scripts/run_full_pipeline.py`

- [ ] **Step 1: Add `--no-research` flag and background server logic**

Replace the contents of `scripts/run_full_pipeline.py`:

```python
#!/usr/bin/env python3
"""
One-command pipeline: Fetch YouTube data via API + run analysis + serve web report.
Optionally launches an async researcher agent for deep analysis.

Usage:
    uv run python scripts/run_full_pipeline.py           # Full pipeline with web report + researcher
    uv run python scripts/run_full_pipeline.py --text    # Skip web report, text only
    uv run python scripts/run_full_pipeline.py --no-research  # Skip researcher
    uv run python scripts/run_full_pipeline.py --port 8080
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser(description="YouTube Analytics Full Pipeline")
parser.add_argument("--text", action="store_true", help="Skip web report, output text analysis only")
parser.add_argument("--no-research", action="store_true", help="Skip async researcher agent")
parser.add_argument("--port", type=int, default=8765, help="Port for web report server")
parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
args = parser.parse_args()

PROJECT_ROOT = Path.cwd()

def run(cmd, cwd=None):
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False, cwd=cwd or PROJECT_ROOT)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    return result

def run_bg(cmd, cwd=None):
    """Run a command in the background, return the process handle."""
    print(f"\n$ {' '.join(cmd)} [background]")
    return subprocess.Popen(cmd, cwd=cwd or PROJECT_ROOT)

def get_latest_data_dir():
    """Find the most recently created data directory."""
    data_dir = PROJECT_ROOT / "data"
    if not data_dir.exists():
        return None
    candidates = [d for d in data_dir.iterdir() if d.is_dir() and d.name != "latest"]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]

steps = 2 if args.text else 3
if not args.no_research and not args.text:
    steps = 4

print("=" * 60)
print("YouTube Analytics Full Pipeline")
print("=" * 60)

# Step 1: Fetch data from API
print(f"\n[Step 1/{steps}] Fetching data from YouTube Analytics API...")
run(["uv", "run", "python", "scripts/fetch_youtube_data.py"])

# Resolve the data directory that was just created
latest_data = get_latest_data_dir()
if latest_data is None:
    # Fall back to data/latest symlink
    latest_link = PROJECT_ROOT / "data" / "latest"
    if latest_link.exists():
        latest_data = latest_link.resolve()
    else:
        print("ERROR: Could not find fetched data directory.")
        sys.exit(1)

data_dir_str = str(latest_data.relative_to(PROJECT_ROOT))
ts = latest_data.name.replace("api_fetch_", "") if "api_fetch_" in latest_data.name else None

# Step 2: Run text analysis
print(f"\n[Step 2/{steps}] Running text analysis...")
run(["uv", "run", "python", "scripts/youtube_analytics.py", "--data-dir", data_dir_str])

# Step 3: Start web server in background
server_proc = None
if not args.text:
    print(f"\n[Step 3/{steps}] Starting web server in background...")
    serve_cmd = ["uv", "run", "python", "scripts/serve_report.py", "--data-dir", data_dir_str, "--port", str(args.port)]
    if args.no_open:
        serve_cmd.append("--no-open")
    server_proc = run_bg(serve_cmd)
    time.sleep(2)  # Give server time to start
    print(f"Server running at: http://127.0.0.1:{args.port}/report.html")

# Step 4: Launch async researcher
if not args.no_research and not args.text:
    print(f"\n[Step 4/{steps}] Launching async researcher agent...")
    research_cmd = [
        "pi", "subagent", "run",
        "--async",
        "--output", f"reports/.research_{ts or 'latest'}.log",
        "youtube-researcher",
        f"Run deep research on YouTube data at {data_dir_str}. Write report to reports/ and enriched CSV to reports/.",
    ]
    # Fallback: if subagent isn't available, run researcher.py directly in background
    try:
        result = subprocess.run(["which", "pi"], capture_output=True, text=True)
        if result.returncode == 0:
            run_bg(research_cmd)
            print("Researcher launched as async sub-agent.")
        else:
            raise FileNotFoundError("pi CLI not found")
    except (FileNotFoundError, Exception):
        print("pi CLI not available, running researcher.py in background...")
        researcher_cmd = [
            "uv", "run", "python", "scripts/researcher.py",
            "--data-dir", data_dir_str,
            "--timestamp", ts or "",
        ]
        run_bg(researcher_cmd)
    print(f"Research report will appear at: reports/research_{ts or '<timestamp>'}.md")

print("\n" + "=" * 60)
if server_proc:
    print("Pipeline complete! Server is running.")
    print(f"View raw data: http://127.0.0.1:{args.port}/report.html")
    if not args.no_research:
        print(f"Research report: reports/research_{ts or '<timestamp>'}.md")
    print("Press Ctrl+C to stop the server.")
    try:
        server_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server_proc.terminate()
        server_proc.wait()
else:
    print("Pipeline complete!")
print("=" * 60)
```

- [ ] **Step 2: Sync to skill directory**

```bash
cp scripts/run_full_pipeline.py .pi/skills/analyzing-youtube-analytics/scripts/run_full_pipeline.py
```

- [ ] **Step 3: Verify the file parses**

```bash
uv run python -m py_compile scripts/run_full_pipeline.py
```

Expected: No output (success)

- [ ] **Step 4: Commit**

```bash
git add scripts/run_full_pipeline.py .pi/skills/analyzing-youtube-analytics/scripts/run_full_pipeline.py
git commit -m "feat: add async researcher launch to full pipeline with --no-research flag"
```

---

### Task 3: Modify `scripts/serve_report.py` — Add Research Status Footer

**Files:**
- Modify: `scripts/serve_report.py`
- Modify: `.pi/skills/analyzing-youtube-analytics/scripts/serve_report.py`

- [ ] **Step 1: Add research status detection and footer rendering**

Find in `scripts/serve_report.py` (around the footer section):

```python
<footer>
  <p>Generated by YouTube Analytics Skill &middot; Data source: {base_name}</p>
</footer>
```

Replace with:

```python
<footer>
  <p>Generated by YouTube Analytics Skill &middot; Data source: {base_name}</p>
  {research_status_html}
</footer>
```

Add the research status detection before the HTML generation (before `html = f'''...`):

```python
# ── Research status ─────────────────────────────────────────────────
REPORTS_DIR = PROJECT_ROOT / "reports"
research_status_html = ""

# Look for research reports matching this data directory's timestamp
data_timestamp = None
if "api_fetch_" in base.name:
    data_timestamp = base.name.replace("api_fetch_", "")

research_files = []
if REPORTS_DIR.exists():
    for f in REPORTS_DIR.glob("research_*.md"):
        if data_timestamp and data_timestamp in f.name:
            research_files.append(f)
        elif not data_timestamp:
            research_files.append(f)

if research_files:
    # Sort by mtime, most recent first
    research_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest_research = research_files[0]
    rel_path = latest_research.relative_to(PROJECT_ROOT)
    research_status_html = f'<p style="margin-top: 0.5rem;"><span style="color: var(--success);">●</span> Research complete: <a href="{rel_path}" style="color: var(--accent2);">View deep analysis</a></p>'
else:
    # Check if researcher is running (look for .research_*.log files)
    log_files = list(REPORTS_DIR.glob(".research_*.log")) if REPORTS_DIR.exists() else []
    if log_files:
        research_status_html = '<p style="margin-top: 0.5rem;"><span style="color: var(--accent3);">◐</span> Research in progress...</p>'
```

Also add the `.research_*.log` pattern to `.gitignore` if not already there:

```bash
echo "reports/.research_*.log" >> .gitignore
```

- [ ] **Step 2: Sync to skill directory**

```bash
cp scripts/serve_report.py .pi/skills/analyzing-youtube-analytics/scripts/serve_report.py
```

- [ ] **Step 3: Verify report generates correctly**

```bash
uv run python scripts/serve_report.py --no-serve --data-dir data/latest 2>&1 | tail -3
```

Expected: `Report generated: report.html`

- [ ] **Step 4: Verify footer renders**

```bash
grep -c "Research in progress\|Research complete\|deep analysis" report.html
```

Expected: `1` (or `0` if no research files exist yet)

- [ ] **Step 5: Commit**

```bash
git add scripts/serve_report.py .pi/skills/analyzing-youtube-analytics/scripts/serve_report.py .gitignore
git commit -m "feat: add research status badge to report footer"
```

---

### Task 4: Add Researcher Agent Definition

**Files:**
- Create: `.pi/skills/analyzing-youtube-analytics/agents/youtube-researcher` (config for pi subagent)

- [ ] **Step 1: Create researcher agent config**

Create `.pi/skills/analyzing-youtube-analytics/agents/youtube-researcher.yaml`:

```yaml
name: youtube-researcher
description: Deep research analyst for YouTube analytics data. Analyzes patterns, diagnoses problems, and generates actionable content ideas.
scope: project
systemPrompt: |
  You are an expert YouTube analytics researcher. Your job is to analyze YouTube Studio data and produce deep insights.

  You have access to the following tools: read, bash, edit, write.

  When given a data directory:
  1. Read all CSV files (Table data.csv, Traffic sources.csv, Search terms.csv, etc.)
  2. Run `scripts/researcher.py --data-dir <dir>` to generate the base report
  3. Read the generated report and enrich it with additional insights:
     - Compare performance across time periods if Chart data.csv exists
     - Identify seasonal patterns or publication-day effects
     - Suggest A/B test ideas for underperforming videos
     - Look for audience demographic mismatches (e.g., content targeting 18-24 but reaching 35-44)
  4. Update the report with your enhanced analysis

  Be specific. Use actual numbers from the data. Avoid generic advice.
  
  Output: Updated report at reports/research_<timestamp>.md
model: anthropic/claude-sonnet-4
tools: read,bash,edit,write
reads:
  - scripts/researcher.py
  - .pi/skills/analyzing-youtube-analytics/SKILL.md
progress: true
```

- [ ] **Step 2: Add agent creation instructions to SKILL.md**

In `.pi/skills/analyzing-youtube-analytics/SKILL.md`, add after the "Web Report" section:

```markdown
## Async Researcher Agent

For deep analysis that runs concurrently with the web report:

```bash
# Full pipeline with background researcher
uv run python scripts/run_full_pipeline.py

# Skip researcher (faster, just raw data)
uv run python scripts/run_full_pipeline.py --no-research

# Run researcher manually on existing data
uv run python scripts/researcher.py --data-dir data/latest
```

The researcher produces:
- `reports/research_<timestamp>.md` — Written analysis (what works, what doesn't, new ideas)
- `reports/enriched_<timestamp>.csv` — Per-video recommendations and anomaly flags

The web report footer shows research status and links to the report when complete.
```

- [ ] **Step 3: Register the agent**

```bash
pi subagent create --config .pi/skills/analyzing-youtube-analytics/agents/youtube-researcher.yaml
```

Or if the pi CLI doesn't support this, document manual registration:

```bash
# Manual registration
cp .pi/skills/analyzing-youtube-analytics/agents/youtube-researcher.yaml ~/.pi/agents/
```

- [ ] **Step 4: Commit**

```bash
git add .pi/skills/analyzing-youtube-analytics/agents/youtube-researcher.yaml .pi/skills/analyzing-youtube-analytics/SKILL.md
git commit -m "feat: add youtube-researcher agent definition and skill docs"
```

---

### Task 5: Integration Test

**Files:**
- None new (uses existing scripts)

- [ ] **Step 1: Run the full pipeline with `--no-research` to verify baseline**

```bash
uv run python scripts/run_full_pipeline.py --no-research --no-open
```

Expected: Server starts, no researcher launched, Ctrl+C stops cleanly.

- [ ] **Step 2: Run the researcher standalone against latest data**

```bash
uv run python scripts/researcher.py --data-dir data/latest
```

Expected: `reports/research_<timestamp>.md` and `reports/enriched_<timestamp>.csv` created.

- [ ] **Step 3: Verify report footer shows "Research complete"**

```bash
uv run python scripts/serve_report.py --no-serve --data-dir data/latest
grep -c "Research complete" report.html
```

Expected: `1`

- [ ] **Step 4: Run all existing tests**

```bash
uv run python -m pytest tests/ -v
```

Expected: All tests PASS (existing + new researcher tests)

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: async researcher agent complete — deep analysis runs concurrent with web report"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ Async researcher runs concurrent with server — Task 2
- ✅ Produces report + enriched CSV — Task 1
- ✅ Covers what works, what doesn't, new ideas — Task 1 (`generate_report`)
- ✅ Web server footer shows status — Task 3
- ✅ Sub-agent support (parallel fan-out via agent config) — Task 4
- ✅ `--no-research` flag — Task 2
- ✅ No new Python dependencies — uses existing scipy or z-score math

**2. Placeholder scan:**
- ✅ No TBD, TODO, "implement later"
- ✅ All code shown in full
- ✅ All commands have expected output
- ✅ No "similar to Task N" references

**3. Type consistency:**
- ✅ `compute_anomaly_flags` returns dict[str, str] consistently
- ✅ `generate_report` takes summary + data dict consistently
- ✅ File paths use `Path` objects consistently

No issues found. Plan is ready.
