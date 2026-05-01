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


def load_data(data_dir):
    """Load all available CSVs from the data directory."""
    data = {}
    summary_path = data_dir / "Table data.csv"
    if summary_path.exists():
        data["summary"] = pd.read_csv(summary_path)
        # Remove Total row if Content column exists
        if "Content" in data["summary"].columns:
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
    
    if "Duration" in df.columns:
        df["Duration (seconds)"] = df["Duration"].apply(parse_dur)
    
    return df


def compute_anomaly_flags(df, col, z_threshold=2.0):
    """Flag videos with z-score outliers in the given column."""
    flags = {}
    mean = df[col].mean()
    std = df[col].std(ddof=0)
    vid_col = "Content" if "Content" in df.columns else "Video"
    if std == 0 or pd.isna(std):
        return {row[vid_col]: "normal" for _, row in df.iterrows()}
    
    for _, row in df.iterrows():
        z = (row[col] - mean) / std
        if z >= z_threshold:
            flags[row[vid_col]] = "spike"
        elif z <= -z_threshold:
            flags[row[vid_col]] = "drop"
        else:
            flags[row[vid_col]] = "normal"
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


def generate_report(summary, data_dir=None):
    """Generate the full markdown research report."""
    summary = compute_derived_metrics(summary)
    
    # Load optional data files
    data = {}
    if data_dir is not None:
        data = load_data(data_dir)
    
    top20 = analyze_top_performers(summary, 0.2)
    bottom20 = analyze_bottom_performers(summary, 0.2)
    
    # Use 'Content' as video ID (matches Table data.csv schema)
    video_id_col = "Content" if "Content" in summary.columns else "Video"
    
    # Per-video diagnosis
    diagnoses = {}
    for _, row in summary.iterrows():
        diagnoses[row[video_id_col]] = diagnose_problems(row)
    
    # Anomaly flags
    view_flags = compute_anomaly_flags(summary, "Views")
    # Rename index to use correct video ID column for mapping
    view_flags = {row[video_id_col]: view_flags.get(row[video_id_col], "normal") for _, row in summary.iterrows()}
    
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


def generate_enriched_csv(summary, data_dir=None):
    """Generate enriched CSV with recommendations and flags."""
    summary = compute_derived_metrics(summary)
    
    top20_median = summary.nlargest(max(1, int(len(summary) * 0.2)), "Views")["Views"].median()
    
    video_id_col = "Content" if "Content" in summary.columns else "Video"
    view_flags = compute_anomaly_flags(summary, "Views")
    diagnoses = {row[video_id_col]: diagnose_problems(row) for _, row in summary.iterrows()}
    recommendations = {row[video_id_col]: compute_recommendation(row, top20_median) for _, row in summary.iterrows()}
    
    enriched = summary.copy()
    vid_col = "Content" if "Content" in enriched.columns else "Video"
    enriched["anomaly_flag"] = enriched[vid_col].map(view_flags)
    enriched["diagnosis"] = enriched[vid_col].map(diagnoses)
    enriched["recommendation"] = enriched[vid_col].map(recommendations)
    enriched["content_opportunity_score"] = 50  # placeholder for v1
    
    # Search gap keywords (placeholder — populated if search data exists)
    enriched["search_gap_keywords"] = ""
    
    return enriched


def main():
    parser = argparse.ArgumentParser(description="Deep research on YouTube analytics data")
    parser.add_argument("--data-dir", type=str, required=True, help="Directory containing CSV data")
    parser.add_argument("--output-dir", type=str, default="reports", help="Directory to write reports")
    parser.add_argument("--timestamp", type=str, default=None, help="Timestamp suffix for output files")
    args = parser.parse_args()
    
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    ts = args.timestamp or datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_path = output_dir / f"research_{ts}.md"
    enriched_path = output_dir / f"enriched_{ts}.csv"
    
    print(f"Loading data from: {data_dir}")
    data = load_data(data_dir)
    
    if "summary" not in data:
        print("ERROR: No Table data.csv found.")
        return 1
    
    summary = data["summary"]
    print(f"Loaded {len(summary)} videos")
    
    # Generate report
    print("Generating research report...")
    report = generate_report(summary, data_dir=data_dir)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report written: {report_path}")
    
    # Generate enriched CSV
    print("Generating enriched data...")
    enriched = generate_enriched_csv(summary, data_dir=data_dir)
    enriched.to_csv(enriched_path, index=False)
    print(f"Enriched CSV written: {enriched_path}")
    
    print("Research complete!")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
