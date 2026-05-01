#!/usr/bin/env python3
"""
YouTube Analytics Report Server
Generates an interactive HTML dashboard and serves it locally.

Usage:
    uv run python scripts/serve_report.py              # Generate + serve on default port
    uv run python scripts/serve_report.py --port 8080  # Custom port
    uv run python scripts/serve_report.py --no-serve   # Just generate report.html
"""

import argparse
import json
import os
import pandas as pd
import numpy as np
import subprocess
import sys
import webbrowser
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread

# ── Argument parsing ────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Serve YouTube Analytics HTML report")
parser.add_argument("--data-dir", type=str, default=None, help="Directory containing CSV data")
parser.add_argument("--port", type=int, default=8765, help="Port for the web server")
parser.add_argument("--no-serve", action="store_true", help="Only generate report.html, don't start server")
parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
args = parser.parse_args()

PROJECT_ROOT = Path.cwd()
OUTPUT_HTML = PROJECT_ROOT / "report.html"

# ── Auto-resolve data directory ────────────────────────────────────
if args.data_dir:
    base = PROJECT_ROOT / args.data_dir
else:
    latest = PROJECT_ROOT / "data" / "latest"
    if latest.exists():
        base = latest.resolve()
    else:
        candidates = list(PROJECT_ROOT.glob("Content*"))
        if candidates:
            base = sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]
        else:
            print("ERROR: No data directory found.")
            sys.exit(1)

print(f"Using data from: {base}")

# ── Load & process data (same logic as youtube_analytics.py) ──────
summary = pd.read_csv(base / "Table data.csv")
summary = summary[summary['Content'] != 'Total'].copy()

num_cols = [
    'Duration', 'Views', 'Watch time (hours)',
    'Subscribers gained', 'Subscribers lost', 'Net subscribers',
    'Likes', 'Dislikes', 'Comments added', 'Shares',
    'Impressions', 'Impressions click-through rate (%)',
    'Average percentage viewed (%)'
]
for col in num_cols:
    if col in summary.columns:
        summary[col] = pd.to_numeric(summary[col], errors='coerce')

def parse_duration(val):
    if pd.isna(val) or val == '':
        return np.nan
    parts = str(val).strip().split(':')
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    else:
        try:
            return float(parts[0])
        except:
            return np.nan

summary['Avg view duration (seconds)'] = summary['Average view duration'].apply(parse_duration)
summary['Duration (seconds)'] = pd.to_numeric(summary['Duration'], errors='coerce')
summary['AVD ratio'] = summary['Avg view duration (seconds)'] / summary['Duration (seconds)']
summary['Watch time per view (minutes)'] = summary['Avg view duration (seconds)'] / 60
summary['Like rate (%)'] = (summary['Likes'] / summary['Views']) * 100
summary['Comment rate (%)'] = (summary['Comments added'] / summary['Views']) * 100
summary['Share rate (%)'] = (summary['Shares'] / summary['Views']) * 100
summary['Engagement rate (%)'] = ((summary['Likes'] + summary['Comments added'] + summary['Shares']) / summary['Views']) * 100
summary['Dislike rate (%)'] = (summary['Dislikes'] / summary['Views']) * 100
summary['Net subscribers'] = summary['Subscribers gained'] - summary['Subscribers lost']
summary['Subscriber conversion rate (%)'] = (summary['Net subscribers'] / summary['Views']) * 100
summary['CTR (%)'] = summary['Impressions click-through rate (%)']
summary['Video publish time'] = pd.to_datetime(summary['Video publish time'], format='%b %d, %Y', errors='coerce')
summary['Days since publish'] = (pd.Timestamp.now() - summary['Video publish time']).dt.days
summary['Views per day'] = summary['Views'] / summary['Days since publish'].clip(lower=1)

def duration_bucket(d):
    if pd.isna(d): return 'Unknown'
    dm = d / 60
    if dm < 1: return '<1 min'
    if dm < 5: return '1-5 min'
    if dm < 10: return '5-10 min'
    return '10+ min'

summary['Duration bucket'] = summary['Duration (seconds)'].apply(duration_bucket)

# ── Load expansion CSVs (optional) ─────────────────────────────────
def load_optional_csv(path):
    if path.exists():
        return pd.read_csv(path)
    return None

traffic_df = load_optional_csv(base / "Traffic sources.csv")
search_df = load_optional_csv(base / "Search terms.csv")
geo_df = load_optional_csv(base / "Geography.csv")
device_df = load_optional_csv(base / "Device type.csv")
content_type_df = load_optional_csv(base / "Content type.csv")
demographics_df = load_optional_csv(base / "Demographics.csv")
retention_df = load_optional_csv(base / "Retention.csv")

# ── Content Type Breakdown aggregates ────────────────────────────────────────
content_type_agg = None
if content_type_df is not None:
    agg = content_type_df.groupby('Content type').agg(
        Videos=('Video', 'nunique'),
        Views=('Views', 'sum'),
        Watch_time=('Watch time (hours)', 'sum'),
        Avg_pct_viewed=('Avg % viewed', 'mean'),
        Subscribers_gained=('Subscribers gained', 'sum'),
    ).reset_index()
    agg.columns = ['Content type', 'Videos', 'Views', 'Watch time (hours)', 'Avg % viewed', 'Subscribers gained']
    agg = agg.sort_values('Views', ascending=False)
    content_type_agg = agg

# ── Traffic source aggregates ─────────────────────────────────────────────
traffic_agg = None
if traffic_df is not None:
    agg = traffic_df.groupby('Traffic source').agg(
        Views=('Views', 'sum'),
        Watch_time=('Watch time (hours)', 'sum'),
    ).reset_index()
    agg.columns = ['Traffic source', 'Views', 'Watch time (hours)']
    agg = agg.sort_values('Views', ascending=False)
    total_views = agg['Views'].sum()
    agg['% of Views'] = (agg['Views'] / total_views * 100).round(1)
    traffic_agg = agg

# ── Per-video dominant traffic source map ────────────────────────────────
video_top_source = {}
if traffic_df is not None:
    for vid, grp in traffic_df.groupby('Video'):
        top = grp.loc[grp['Views'].idxmax()]
        video_top_source[vid] = top['Traffic source']

# ── Geography aggregates ───────────────────────────────────────────────────
geo_top10 = None
if geo_df is not None:
    agg = geo_df.groupby('Country').agg(
        Views=('Views', 'sum'),
        Watch_time=('Watch time (hours)', 'sum'),
        Subscribers_gained=('Subscribers gained', 'sum'),
    ).reset_index()
    agg.columns = ['Country', 'Views', 'Watch time (hours)', 'Subscribers gained']
    agg = agg.sort_values('Views', ascending=False).head(10)
    geo_top10 = agg

# ── Device breakdown aggregates ──────────────────────────────────────────
device_agg = None
if device_df is not None:
    agg = device_df.groupby('Device').agg(
        Views=('Views', 'sum'),
        Watch_time=('Watch time (hours)', 'sum'),
    ).reset_index()
    agg.columns = ['Device', 'Views', 'Watch time (hours)']
    agg = agg.sort_values('Views', ascending=False)
    device_agg = agg

# ── Demographics aggregates ─────────────────────────────────────────────────
demographics_agg = None
if demographics_df is not None:
    agg = demographics_df.groupby(['Age group', 'Gender']).agg(
        Viewer_pct=('Viewer %', 'mean'),
    ).reset_index()
    agg.columns = ['Age group', 'Gender', 'Viewer %']
    demographics_agg = agg.sort_values(['Age group', 'Gender'])

# ── Retention data ─────────────────────────────────────────────────────────
retention_videos = None
retention_records = None
if retention_df is not None:
    retention_videos = (
        retention_df[['Video', 'Video title']]
        .drop_duplicates('Video')
        .to_dict('records')
    )
    retention_records = json.loads(retention_df.fillna('').to_json(orient='records', date_format='iso'))

# ── Search terms table ──────────────────────────────────────────────────────
search_table = None
if search_df is not None:
    search_table = search_df.sort_values('Views', ascending=False).reset_index(drop=True)
    search_table.insert(0, '#', search_table.index + 1)

# ── Per-video content type map ──────────────────────────────────────────────
video_content_type = {}
if content_type_df is not None:
    for _, row in content_type_df.iterrows():
        video_content_type[row['Video']] = row['Content type']

# ── Build report data structures ────────────────────────────────────
def df_to_records(df):
    """Convert DataFrame to list of dicts, handling NaN."""
    return json.loads(df.fillna('').to_json(orient='records', date_format='iso'))

def safe_round(val, decimals=2):
    if pd.isna(val): return None
    return round(float(val), decimals)

# Channel snapshot
channel_snapshot = {
    "total_views": int(summary['Views'].sum()),
    "total_watch_time": safe_round(summary['Watch time (hours)'].sum(), 1),
    "total_subs_gained": int(summary['Subscribers gained'].sum()),
    "total_subs_lost": int(summary['Subscribers lost'].sum()),
    "net_subs": int(summary['Net subscribers'].sum()),
    "total_likes": int(summary['Likes'].sum()),
    "total_comments": int(summary['Comments added'].sum()),
    "total_shares": int(summary['Shares'].sum()),
    "total_impressions": int(summary['Impressions'].sum()),
    "overall_ctr": safe_round((summary['Views'].sum() / summary['Impressions'].sum()) * 100, 2) if summary['Impressions'].sum() > 0 else None,
    "overall_like_rate": safe_round((summary['Likes'].sum() / summary['Views'].sum()) * 100, 2),
    "overall_engagement_rate": safe_round(((summary['Likes'].sum()+summary['Comments added'].sum()+summary['Shares'].sum()) / summary['Views'].sum()) * 100, 2),
    "videos_analyzed": len(summary),
}

# ── Serialize expansion JSON for f-string interpolation ──────────────────────
content_type_json = json.dumps(df_to_records(content_type_agg)) if content_type_agg is not None else '[]'
traffic_json = json.dumps(df_to_records(traffic_agg)) if traffic_agg is not None else '[]'
search_json = json.dumps(df_to_records(search_table)) if search_table is not None else '[]'
demo_json = json.dumps(df_to_records(demographics_agg)) if demographics_agg is not None else '[]'
retention_json = json.dumps(retention_records) if retention_records is not None else '[]'
geo_label_json = json.dumps(list(geo_top10['Country'])) if geo_top10 is not None else '[]'
geo_views_json = json.dumps(list(geo_top10['Views'])) if geo_top10 is not None else '[]'
device_label_json = json.dumps(list(device_agg['Device'])) if device_agg is not None else '[]'
device_views_json = json.dumps(list(device_agg['Views'])) if device_agg is not None else '[]'

# Top/bottom videos
top_cols = ['Video title', 'Content', 'Views', 'Watch time (hours)', 'Likes', 'Comments added',
            'Shares', 'Net subscribers', 'CTR (%)', 'AVD ratio', 'Engagement rate (%)']
top10 = summary.nlargest(10, 'Views')[top_cols]
bottom10 = summary.nsmallest(10, 'Views')[top_cols]

# Segment analysis
dur_agg = summary.groupby('Duration bucket').agg({
    'Views': ['count', 'sum', 'mean', 'median'],
    'Watch time (hours)': 'sum',
    'CTR (%)': 'mean',
    'AVD ratio': 'mean',
    'Engagement rate (%)': 'mean',
    'Subscriber conversion rate (%)': 'mean',
    'Average percentage viewed (%)': 'mean',
}).round(2)
dur_agg.columns = ['Videos', 'Total Views', 'Avg Views', 'Median Views', 'Total WT',
                   'Avg CTR', 'Avg AVD', 'Avg Eng Rate', 'Avg Sub Conv', 'Avg % Viewed']
dur_agg = dur_agg.sort_values('Total Views', ascending=False).reset_index()

# Correlations
corr_cols = ['Views', 'CTR (%)', 'AVD ratio', 'Engagement rate (%)',
             'Subscriber conversion rate (%)', 'Like rate (%)', 'Comment rate (%)',
             'Share rate (%)', 'Average percentage viewed (%)',
             'Watch time per view (minutes)']
available_corr_cols = [c for c in corr_cols if c in summary.columns]
corr = summary[available_corr_cols].corr()['Views'].drop('Views').sort_values(ascending=False)
correlations = {k: safe_round(v, 3) for k, v in corr.items()}

# Top 20% vs bottom 20%
top20 = summary.nlargest(max(1, int(len(summary) * 0.2)), 'Views')
bottom20 = summary.nsmallest(max(1, int(len(summary) * 0.2)), 'Views')
top_vs_bottom = {
    "top_count": len(top20),
    "bottom_count": len(bottom20),
    "avg_views_top": safe_round(top20['Views'].mean(), 0),
    "avg_views_bottom": safe_round(bottom20['Views'].mean(), 0),
    "avg_ctr_top": safe_round(top20['CTR (%)'].mean(), 2),
    "avg_ctr_bottom": safe_round(bottom20['CTR (%)'].mean(), 2),
    "avg_avd_top": safe_round(top20['AVD ratio'].mean(), 2),
    "avg_avd_bottom": safe_round(bottom20['AVD ratio'].mean(), 2),
    "avg_eng_top": safe_round(top20['Engagement rate (%)'].mean(), 2),
    "avg_eng_bottom": safe_round(bottom20['Engagement rate (%)'].mean(), 2),
    "avg_subconv_top": safe_round(top20['Subscriber conversion rate (%)'].mean(), 3),
    "avg_subconv_bottom": safe_round(bottom20['Subscriber conversion rate (%)'].mean(), 3),
    "avg_pct_top": safe_round(top20['Average percentage viewed (%)'].mean(), 1),
    "avg_pct_bottom": safe_round(bottom20['Average percentage viewed (%)'].mean(), 1),
}

# Deep dives
eng_filter = summary[summary['Views'] >= 100].nlargest(5, 'Engagement rate (%)')
like_filter = summary[summary['Views'] >= 100].nlargest(5, 'Like rate (%)')
sub_filter = summary[summary['Views'] >= 100].nlargest(5, 'Subscriber conversion rate (%)')
momentum = summary.nlargest(5, 'Views per day')

# Funnel diagnosis
funnel_data = []
for idx, row in summary.iterrows():
    ctr = row['CTR (%)']
    pct = row['Average percentage viewed (%)']
    disc = "Strong" if pd.notna(ctr) and ctr >= 8 else ("Weak" if pd.notna(ctr) and ctr < 5 else "Moderate")
    ret = "Strong" if pd.notna(pct) and pct >= 70 else ("Weak" if pd.notna(pct) and pct < 40 else "Moderate")
    funnel_data.append({
        "title": row['Video title'],
        "views": int(row['Views']),
        "ctr": safe_round(ctr, 2),
        "pct_viewed": safe_round(pct, 1),
        "discovery": disc,
        "retention": ret,
        "content_type": video_content_type.get(row['Content'], ''),
        "top_source": video_top_source.get(row['Content'], ''),
    })

# Weekly trend
trend_data = []
totals_path = base / "Totals.csv"
if totals_path.exists():
    totals = pd.read_csv(totals_path)
    totals['Date'] = pd.to_datetime(totals['Date'])
    totals = totals.sort_values('Date')
    wt_col = None
    for c in ['Watch time (hours)', 'YouTube Premium watch time (hours)', 'estimatedMinutesWatched']:
        if c in totals.columns:
            wt_col = c
            break
    if wt_col:
        trend_data = [
            {"date": str(r['Date']), "value": safe_round(r[wt_col], 2)}
            for _, r in totals.iterrows()
        ]

# ── Generate HTML ───────────────────────────────────────────────────
html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>YouTube Analytics Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0f0f23;
    --card: #1a1a2e;
    --card-hover: #252542;
    --text: #e0e0e0;
    --text-dim: #8888aa;
    --accent: #ff6b35;
    --accent2: #00d4aa;
    --accent3: #f0c040;
    --danger: #ff4757;
    --success: #2ed573;
    --border: #2a2a4a;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
  }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 2rem; }}
  header {{
    text-align: center;
    padding: 3rem 1rem;
    background: linear-gradient(135deg, var(--card) 0%, #16162a 100%);
    border-bottom: 2px solid var(--accent);
    margin-bottom: 2rem;
  }}
  header h1 {{ font-size: 2.5rem; color: var(--accent); margin-bottom: 0.5rem; }}
  header p {{ color: var(--text-dim); }}
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }}
  .kpi {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    text-align: center;
    transition: transform 0.2s, background 0.2s;
  }}
  .kpi:hover {{ transform: translateY(-4px); background: var(--card-hover); }}
  .kpi .value {{ font-size: 2rem; font-weight: 700; color: var(--accent2); }}
  .kpi .label {{ font-size: 0.85rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 0.25rem; }}
  section {{ margin-bottom: 3rem; }}
  h2 {{
    font-size: 1.5rem;
    color: var(--accent);
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }}
  h3 {{ font-size: 1.1rem; color: var(--accent3); margin: 1.5rem 0 0.75rem; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    font-size: 0.9rem;
  }}
  th, td {{ padding: 0.75rem 1rem; text-align: left; }}
  th {{ background: #222244; color: var(--accent3); font-weight: 600; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.5px; }}
  tr {{ border-bottom: 1px solid var(--border); }}
  tr:last-child {{ border-bottom: none; }}
  tr:hover {{ background: var(--card-hover); }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .badge {{
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
  }}
  .badge-strong {{ background: rgba(46,213,115,0.15); color: var(--success); }}
  .badge-moderate {{ background: rgba(240,192,64,0.15); color: var(--accent3); }}
  .badge-weak {{ background: rgba(255,71,87,0.15); color: var(--danger); }}
  .chart-container {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
  }}
  .chart-row {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
    gap: 1.5rem;
  }}
  .comparison {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
  }}
  .comparison-box {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
  }}
  .comparison-box h4 {{ color: var(--accent2); margin-bottom: 1rem; }}
  .comparison-box.bottom h4 {{ color: var(--danger); }}
  .stat-row {{ display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid var(--border); }}
  .stat-row:last-child {{ border-bottom: none; }}
  .stat-label {{ color: var(--text-dim); }}
  .stat-value {{ font-weight: 600; }}
  .video-row {{ font-size: 0.85rem; }}
  .video-row td:first-child {{ max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .topic-tag {{ color: var(--text-dim); font-size: 0.8rem; }}
  footer {{
    text-align: center;
    padding: 2rem;
    color: var(--text-dim);
    font-size: 0.85rem;
    border-top: 1px solid var(--border);
    margin-top: 3rem;
  }}
  @media (max-width: 768px) {{
    .container {{ padding: 1rem; }}
    .comparison {{ grid-template-columns: 1fr; }}
    .chart-row {{ grid-template-columns: 1fr; }}
    header h1 {{ font-size: 1.75rem; }}
    th, td {{ padding: 0.5rem; font-size: 0.8rem; }}
  }}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>YouTube Analytics Report</h1>
  <p>{base.name} &middot; Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</header>

<section>
  <h2>Channel Snapshot</h2>
  <div class="kpi-grid">
    <div class="kpi"><div class="value">{channel_snapshot['total_views']:,}</div><div class="label">Total Views</div></div>
    <div class="kpi"><div class="value">{channel_snapshot['total_watch_time']:,.1f}h</div><div class="label">Watch Time</div></div>
    <div class="kpi"><div class="value">{channel_snapshot['net_subs']:+,.0f}</div><div class="label">Net Subscribers</div></div>
    <div class="kpi"><div class="value">{channel_snapshot['total_likes']:,}</div><div class="label">Likes</div></div>
    <div class="kpi"><div class="value">{channel_snapshot['total_comments']:,}</div><div class="label">Comments</div></div>
    <div class="kpi"><div class="value">{channel_snapshot['total_shares']:,}</div><div class="label">Shares</div></div>
    <div class="kpi"><div class="value">{channel_snapshot['total_impressions']:,}</div><div class="label">Impressions</div></div>
    <div class="kpi"><div class="value">{f"{channel_snapshot['overall_ctr']:.2f}" if channel_snapshot['overall_ctr'] is not None else 'N/A'}%</div><div class="label">Overall CTR</div></div>
    <div class="kpi"><div class="value">{channel_snapshot['overall_engagement_rate']:.2f}%</div><div class="label">Engagement Rate</div></div>
    <div class="kpi"><div class="value">{channel_snapshot['videos_analyzed']}</div><div class="label">Videos</div></div>
  </div>
</section>
'''

# ── Content Type Breakdown ──────────────────────────────────────────
if content_type_agg is not None:
    html += f'''
<section>
  <h2>Content Type Breakdown</h2>
  <div class="chart-row">
    <div class="chart-container">
      <canvas id="contentTypeChart"></canvas>
    </div>
    <div class="chart-container" style="overflow: auto;">
      <table>
        <thead>
          <tr>
            <th>Content type</th>
            <th class="num">Videos</th>
            <th class="num">Views</th>
            <th class="num">WT (h)</th>
            <th class="num">Avg % Viewed</th>
            <th class="num">Subs gained</th>
          </tr>
        </thead>
        <tbody>
'''
    for _, row in content_type_agg.iterrows():
        html += f'''          <tr>
            <td>{row['Content type']}</td>
            <td class="num">{int(row['Videos'])}</td>
            <td class="num">{int(row['Views']):,}</td>
            <td class="num">{safe_round(row['Watch time (hours)'], 1)}</td>
            <td class="num">{safe_round(row['Avg % viewed'], 1)}%</td>
            <td class="num">{int(row['Subscribers gained']):+}</td>
          </tr>
'''
    html += '''        </tbody>
      </table>
    </div>
  </div>
</section>
'''

# ── Traffic Sources ────────────────────────────────────────────────
if traffic_agg is not None:
    html += f'''
<section>
  <h2>Traffic Sources</h2>
  <div class="chart-row">
    <div class="chart-container">
      <canvas id="trafficDonutChart"></canvas>
    </div>
    <div class="chart-container" style="overflow: auto;">
      <table>
        <thead>
          <tr>
            <th>Traffic source</th>
            <th class="num">Views</th>
            <th class="num">WT (h)</th>
            <th class="num">% of Views</th>
          </tr>
        </thead>
        <tbody>
'''
    for _, row in traffic_agg.iterrows():
        html += f'''          <tr>
            <td>{row['Traffic source']}</td>
            <td class="num">{int(row['Views']):,}</td>
            <td class="num">{safe_round(row['Watch time (hours)'], 1)}</td>
            <td class="num">{row['% of Views']}%</td>
          </tr>
'''
    html += '''        </tbody>
      </table>
    </div>
  </div>
</section>
'''

# ── Search Terms ────────────────────────────────────────────────────
if search_table is not None:
    html += '''
<section>
  <h2>Top Search Terms</h2>
  <table>
    <thead>
      <tr>
        <th class="num">#</th>
        <th>Search term</th>
        <th>Video</th>
        <th class="num">Views</th>
        <th class="num">WT (h)</th>
      </tr>
    </thead>
    <tbody>
'''
    for _, row in search_table.iterrows():
        html += f'''      <tr>
        <td class="num">{int(row['#'])}</td>
        <td style="font-weight: 600;">{row['Search term']}</td>
        <td style="color: var(--text-dim); max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{row['Video title'][:55]}</td>
        <td class="num">{int(row['Views']):,}</td>
        <td class="num">{safe_round(row['Watch time (hours)'], 1)}</td>
      </tr>
'''
    html += '''    </tbody>
  </table>
</section>
'''

# ── Geography + Device Breakdown ────────────────────────────────────
if geo_top10 is not None or device_agg is not None:
    html += f'''
<section>
  <h2>Audience Insights</h2>
  <div class="chart-row">
'''
    if geo_top10 is not None:
        html += f'''    <div class="chart-container">
      <canvas id="geoChart"></canvas>
    </div>
'''
    if device_agg is not None:
        html += f'''    <div class="chart-container">
      <canvas id="deviceChart"></canvas>
    </div>
'''
    html += '''  </div>
</section>
'''

# ── Demographics ───────────────────────────────────────────────────
if demographics_agg is not None:
    html += f'''
<section>
  <h2>Demographics</h2>
  <div class="chart-container" style="max-width: 600px;">
    <canvas id="demoChart"></canvas>
  </div>
</section>
'''

# ── Retention Curves ────────────────────────────────────────────────
if retention_df is not None:
    default_video_id = retention_videos[0]['Video'] if retention_videos else ''
    default_video_title = retention_videos[0]['Video title'] if retention_videos else ''

    html += f'''
<section>
  <h2>Retention Curves</h2>
  <div class="chart-container">
    <div style="margin-bottom: 1rem;">
      <label for="retentionSelect" style="color: var(--text-dim); font-size: 0.85rem; margin-right: 0.5rem;">Video:</label>
      <select id="retentionSelect" onchange="updateRetentionChart(this.value)" style="background: var(--card); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 0.4rem 1rem; min-width: 320px;">
'''
    for v in retention_videos:
        sel = 'selected' if v['Video'] == default_video_id else ''
        html += f'''        <option value="{v['Video']}" {sel}>{v['Video title'][:70]}</option>
'''
    html += '''      </select>
    </div>
    <canvas id="retentionChart"></canvas>
  </div>
</section>
'''

html += '''
<section>
  <h2>Performance Charts</h2>
  <div class="chart-row">
    <div class="chart-container">
      <canvas id="viewsChart"></canvas>
    </div>
    <div class="chart-container">
      <canvas id="corrChart"></canvas>
    </div>
  </div>
'''
if trend_data:
    html += '''  <div class="chart-container"><canvas id="trendChart"></canvas></div>
'''
html += '''</section>

<section>
  <h2>Top 10 Videos</h2>
  <table>
    <thead>
      <tr>
        <th>Video</th>
        <th class="num">Views</th>
        <th class="num">WT (h)</th>
        <th class="num">Likes</th>
        <th class="num">Comments</th>
        <th class="num">CTR</th>
        <th class="num">AVD</th>
        <th class="num">Eng %</th>
        <th class="num">Net Subs</th>
        <th>Content type</th>
        <th>Top source</th>
      </tr>
    </thead>
    <tbody>
'''

for _, row in top10.iterrows():
    html += f'''      <tr class="video-row">
        <td title="{row['Video title']}">{row['Video title'][:55]}</td>
        <td class="num">{int(row['Views']):,}</td>
        <td class="num">{safe_round(row['Watch time (hours)'], 1)}</td>
        <td class="num">{int(row['Likes']):,}</td>
        <td class="num">{int(row['Comments added']):,}</td>
        <td class="num">{safe_round(row['CTR (%)'], 2)}%</td>
        <td class="num">{safe_round(row['AVD ratio'], 2)}</td>
        <td class="num">{safe_round(row['Engagement rate (%)'], 2)}%</td>
        <td class="num">{int(row['Net subscribers']):+}</td>
        <td>{video_content_type.get(row['Content'], '')}</td>
        <td>{video_top_source.get(row['Content'], '')}</td>
      </tr>
'''

html += '''    </tbody>
  </table>

  <h2>Bottom 10 Videos</h2>
  <table>
    <thead>
      <tr>
        <th>Video</th>
        <th class="num">Views</th>
        <th class="num">WT (h)</th>
        <th class="num">Likes</th>
        <th class="num">Comments</th>
        <th class="num">CTR</th>
        <th class="num">AVD</th>
        <th class="num">Eng %</th>
        <th class="num">Net Subs</th>
        <th>Content type</th>
        <th>Top source</th>
      </tr>
    </thead>
    <tbody>
'''

for _, row in bottom10.iterrows():
    html += f'''      <tr class="video-row">
        <td title="{row['Video title']}">{row['Video title'][:55]}</td>
        <td class="num">{int(row['Views']):,}</td>
        <td class="num">{safe_round(row['Watch time (hours)'], 1)}</td>
        <td class="num">{int(row['Likes']):,}</td>
        <td class="num">{int(row['Comments added']):,}</td>
        <td class="num">{safe_round(row['CTR (%)'], 2)}%</td>
        <td class="num">{safe_round(row['AVD ratio'], 2)}</td>
        <td class="num">{safe_round(row['Engagement rate (%)'], 2)}%</td>
        <td class="num">{int(row['Net subscribers']):+}</td>
        <td>{video_content_type.get(row['Content'], '')}</td>
        <td>{video_top_source.get(row['Content'], '')}</td>
      </tr>
'''

html += '''    </tbody>
  </table>
</section>

<section>
  <h2>Segment Analysis: By Duration</h2>
  <table>
    <thead>
      <tr>
        <th>Duration</th>
        <th class="num">Videos</th>
        <th class="num">Total Views</th>
        <th class="num">Avg Views</th>
        <th class="num">Median Views</th>
        <th class="num">Avg CTR</th>
        <th class="num">Avg AVD</th>
        <th class="num">Avg Eng %</th>
        <th class="num">Avg Sub Conv</th>
        <th class="num">Avg % Viewed</th>
      </tr>
    </thead>
    <tbody>
'''

for _, row in dur_agg.iterrows():
    html += f'''      <tr>
        <td>{row['Duration bucket']}</td>
        <td class="num">{int(row['Videos'])}</td>
        <td class="num">{int(row['Total Views']):,}</td>
        <td class="num">{safe_round(row['Avg Views'], 0):,.0f}</td>
        <td class="num">{safe_round(row['Median Views'], 0):,.0f}</td>
        <td class="num">{safe_round(row['Avg CTR'], 2)}%</td>
        <td class="num">{safe_round(row['Avg AVD'], 2)}</td>
        <td class="num">{safe_round(row['Avg Eng Rate'], 2)}%</td>
        <td class="num">{safe_round(row['Avg Sub Conv'], 3)}%</td>
        <td class="num">{safe_round(row['Avg % Viewed'], 1)}%</td>
      </tr>
'''

html += f'''    </tbody>
  </table>
</section>

<section>
  <h2>Top 20% vs Bottom 20%</h2>
  <div class="comparison">
    <div class="comparison-box">
      <h4>Top 20% ({top_vs_bottom['top_count']} videos)</h4>
      <div class="stat-row"><span class="stat-label">Avg Views</span><span class="stat-value">{top_vs_bottom['avg_views_top']:,.0f}</span></div>
      <div class="stat-row"><span class="stat-label">Avg CTR</span><span class="stat-value">{top_vs_bottom['avg_ctr_top']:.2f}%</span></div>
      <div class="stat-row"><span class="stat-label">Avg AVD</span><span class="stat-value">{top_vs_bottom['avg_avd_top']:.2f}</span></div>
      <div class="stat-row"><span class="stat-label">Avg Eng Rate</span><span class="stat-value">{top_vs_bottom['avg_eng_top']:.2f}%</span></div>
      <div class="stat-row"><span class="stat-label">Avg Sub Conv</span><span class="stat-value">{top_vs_bottom['avg_subconv_top']:.3f}%</span></div>
      <div class="stat-row"><span class="stat-label">Avg % Viewed</span><span class="stat-value">{top_vs_bottom['avg_pct_top']:.1f}%</span></div>
    </div>
    <div class="comparison-box bottom">
      <h4>Bottom 20% ({top_vs_bottom['bottom_count']} videos)</h4>
      <div class="stat-row"><span class="stat-label">Avg Views</span><span class="stat-value">{top_vs_bottom['avg_views_bottom']:,.0f}</span></div>
      <div class="stat-row"><span class="stat-label">Avg CTR</span><span class="stat-value">{top_vs_bottom['avg_ctr_bottom']:.2f}%</span></div>
      <div class="stat-row"><span class="stat-label">Avg AVD</span><span class="stat-value">{top_vs_bottom['avg_avd_bottom']:.2f}</span></div>
      <div class="stat-row"><span class="stat-label">Avg Eng Rate</span><span class="stat-value">{top_vs_bottom['avg_eng_bottom']:.2f}%</span></div>
      <div class="stat-row"><span class="stat-label">Avg Sub Conv</span><span class="stat-value">{top_vs_bottom['avg_subconv_bottom']:.3f}%</span></div>
      <div class="stat-row"><span class="stat-label">Avg % Viewed</span><span class="stat-value">{top_vs_bottom['avg_pct_bottom']:.1f}%</span></div>
    </div>
  </div>
</section>

<section>
  <h2>Funnel Diagnosis</h2>
  <table>
    <thead>
      <tr>
        <th>Video</th>
        <th class="num">Views</th>
        <th class="num">CTR</th>
        <th class="num">% Viewed</th>
        <th>Discovery</th>
        <th>Retention</th>
        <th>Type</th>
        <th>Top source</th>
      </tr>
    </thead>
    <tbody>
'''

for v in funnel_data:
    disc_badge = f'<span class="badge badge-{v["discovery"].lower()}">{v["discovery"]}</span>'
    ret_badge = f'<span class="badge badge-{v["retention"].lower()}">{v["retention"]}</span>'
    html += f'''      <tr class="video-row">
        <td title="{v['title']}">{v['title'][:55]}</td>
        <td class="num">{v['views']:,}</td>
        <td class="num">{v['ctr']}%</td>
        <td class="num">{v['pct_viewed']}%</td>
        <td>{disc_badge}</td>
        <td>{ret_badge}</td>
        <td>{v['content_type']}</td>
        <td>{v['top_source']}</td>
      </tr>
'''

html += '''    </tbody>
  </table>
</section>

<section>
  <h2>Deep Dives</h2>
  <h3>Highest Engagement Rate (min 100 views)</h3>
  <table>
    <thead><tr><th>Video</th><th class="num">Views</th><th class="num">Likes</th><th class="num">Comments</th><th class="num">Shares</th><th class="num">Eng %</th></tr></thead>
    <tbody>
'''

for _, row in eng_filter.iterrows():
    html += f'''      <tr class="video-row">
        <td title="{row['Video title']}">{row['Video title'][:55]}</td>
        <td class="num">{int(row['Views']):,}</td>
        <td class="num">{int(row['Likes']):,}</td>
        <td class="num">{int(row['Comments added']):,}</td>
        <td class="num">{int(row['Shares']):,}</td>
        <td class="num">{safe_round(row['Engagement rate (%)'], 2)}%</td>
      </tr>
'''

html += '''    </tbody>
  </table>

  <h3>Best Subscriber Conversion (min 100 views)</h3>
  <table>
    <thead><tr><th>Video</th><th class="num">Views</th><th class="num">Gained</th><th class="num">Lost</th><th class="num">Net</th><th class="num">Conv %</th></tr></thead>
    <tbody>
'''

for _, row in sub_filter.iterrows():
    html += f'''      <tr class="video-row">
        <td title="{row['Video title']}">{row['Video title'][:55]}</td>
        <td class="num">{int(row['Views']):,}</td>
        <td class="num">{int(row['Subscribers gained']):,}</td>
        <td class="num">{int(row['Subscribers lost']):,}</td>
        <td class="num">{int(row['Net subscribers']):+}</td>
        <td class="num">{safe_round(row['Subscriber conversion rate (%)'], 3)}%</td>
      </tr>
'''

html += '''    </tbody>
  </table>

  <h3>Top Momentum (views per day)</h3>
  <table>
    <thead><tr><th>Video</th><th class="num">Views</th><th class="num">Age (days)</th><th class="num">Views/Day</th></tr></thead>
    <tbody>
'''

for _, row in momentum.iterrows():
    html += f'''      <tr class="video-row">
        <td title="{row['Video title']}">{row['Video title'][:55]}</td>
        <td class="num">{int(row['Views']):,}</td>
        <td class="num">{int(row['Days since publish'])}</td>
        <td class="num">{safe_round(row['Views per day'], 1)}</td>
      </tr>
'''

html += '''    </tbody>
  </table>
</section>

<footer>
  <p>Generated by YouTube Analytics Skill &middot; Data source: {base_name}</p>
</footer>

</div>

<script>
// ── Chart data ──────────────────────────────────────────────────────
const funnelData = {funnel_json};
const corrData = {corr_json};
const trendData = {trend_json};

// New expansion data
const contentTypeChartData = {content_type_json};
const trafficChartData = {traffic_json};
const searchChartData = {search_json};
const demoChartData = {demo_json};
const retentionChartData = {retention_json};
const geoChartData = {geo_label_json}.map((label, i) => ({{'Country': label, 'Views': {geo_views_json}[i]}}));
const deviceChartData = {device_label_json}.map((label, i) => ({{'Device': label, 'Views': {device_views_json}[i]}}));

Chart.defaults.color = '#8888aa';
Chart.defaults.borderColor = '#2a2a4a';

// Content type bar chart
if (contentTypeChartData.length > 0) {{
  new Chart(document.getElementById('contentTypeChart'), {{
    type: 'bar',
    data: {{
      labels: contentTypeChartData.map(d => d['Content type']),
      datasets: [{{
        label: 'Views',
        data: contentTypeChartData.map(d => d['Views']),
        backgroundColor: '#ff6b35',
        borderRadius: 6,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ title: {{ display: true, text: 'Views by Content Type', color: '#e0e0e0' }} }},
      scales: {{ y: {{ beginAtZero: true }} }}
    }}
  }});
}}

// Traffic sources donut chart
if (trafficChartData.length > 0) {{
  new Chart(document.getElementById('trafficDonutChart'), {{
    type: 'doughnut',
    data: {{
      labels: trafficChartData.map(d => d['Traffic source']),
      datasets: [{{
        data: trafficChartData.map(d => d['Views']),
        backgroundColor: ['#ff6b35','#00d4aa','#f0c040','#6c5ce7','#e056a0','#888','#a29bfe','#fd79a8'],
        borderWidth: 0,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        title: {{ display: true, text: 'Traffic Source Mix', color: '#e0e0e0' }},
        legend: {{ position: 'bottom', labels: {{ color: '#8888aa', padding: 12 }} }}
      }}
    }}
  }});
}}

// Geography horizontal bar chart
if (geoChartData.length > 0) {{
  new Chart(document.getElementById('geoChart'), {{
    type: 'bar',
    data: {{
      labels: geoChartData.map(d => d['Country']),
      datasets: [{{
        label: 'Views',
        data: geoChartData.map(d => d['Views']),
        backgroundColor: '#00d4aa',
        borderRadius: 4,
      }}]
    }},
    options: {{
      indexAxis: 'y',
      responsive: true,
      plugins: {{ title: {{ display: true, text: 'Top Countries by Views', color: '#e0e0e0' }} }},
      scales: {{ x: {{ beginAtZero: true }} }}
    }}
  }});
}}

// Device breakdown donut chart
if (deviceChartData.length > 0) {{
  new Chart(document.getElementById('deviceChart'), {{
    type: 'doughnut',
    data: {{
      labels: deviceChartData.map(d => d['Device']),
      datasets: [{{
        data: deviceChartData.map(d => d['Views']),
        backgroundColor: ['#ff6b35','#00d4aa','#f0c040','#6c5ce7'],
        borderWidth: 0,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        title: {{ display: true, text: 'Device Breakdown', color: '#e0e0e0' }},
        legend: {{ position: 'bottom', labels: {{ color: '#8888aa', padding: 12 }} }}
      }}
    }}
  }});
}}

// Demographics stacked bar chart
if (demoChartData.length > 0) {{
  const ages = [...new Set(demoChartData.map(d => d['Age group']))];
  const genders = [...new Set(demoChartData.map(d => d['Gender']))];
  const genderColors = {{ 'male': '#ff6b35', 'female': '#00d4aa', 'user_specified': '#f0c040' }};
  new Chart(document.getElementById('demoChart'), {{
    type: 'bar',
    data: {{
      labels: ages,
      datasets: genders.map(g => ({{
        label: g,
        data: ages.map(a => {{
          const row = demoChartData.find(d => d['Age group'] === a && d['Gender'] === g);
          return row ? row['Viewer %'] : 0;
        }}),
        backgroundColor: genderColors[g] || '#888',
      }}))
    }},
    options: {{
      responsive: true,
      plugins: {{
        title: {{ display: true, text: 'Audience Demographics by Age & Gender', color: '#e0e0e0' }},
        legend: {{ position: 'bottom', labels: {{ color: '#8888aa', padding: 12 }} }}
      }},
      scales: {{
        x: {{ stacked: true }},
        y: {{ stacked: true, beginAtZero: true, max: 100, title: {{ display: true, text: 'Viewer %', color: '#8888aa' }} }}
      }}
    }}
  }});
}}

// Retention curve chart
if (retentionChartData.length > 0) {{
  const defaultVid = retentionChartData[0] && retentionChartData[0]['Video'];
  let retChart = null;
  function updateRetentionChart(videoId) {{
    const rows = retentionChartData.filter(d => d['Video'] === videoId);
    if (!rows.length) return;
    const labels = rows.map(d => (d['Elapsed ratio'] * 100).toFixed(0) + '%');
    const watchRatio = rows.map(d => d['Audience watch ratio']);
    const relRet = rows.map(d => d['Relative retention']);
    if (!retChart) {{
      retChart = new Chart(document.getElementById('retentionChart'), {{
        type: 'line',
        data: {{
          labels: labels,
          datasets: [
            {{
              label: 'Watch ratio',
              data: watchRatio,
              borderColor: '#ff6b35',
              backgroundColor: 'rgba(255,107,53,0.1)',
              fill: false,
              tension: 0.3,
              pointRadius: 3,
            }},
            {{
              label: 'Relative retention',
              data: relRet,
              borderColor: '#00d4aa',
              borderDash: [6, 4],
              fill: false,
              tension: 0.3,
              pointRadius: 2,
            }}
          ]
        }},
        options: {{
          responsive: true,
          plugins: {{
            title: {{ display: true, text: 'Audience Retention', color: '#e0e0e0' }},
            legend: {{ position: 'bottom', labels: {{ color: '#8888aa', padding: 12 }} }}
          }},
          scales: {{
            x: {{ title: {{ display: true, text: '% of Video', color: '#8888aa' }} }},
            y: {{ beginAtZero: true, title: {{ display: true, text: 'Retention Ratio', color: '#8888aa' }} }}
          }}
        }}
      }});
    }} else {{
      retChart.data.labels = labels;
      retChart.data.datasets[0].data = watchRatio;
      retChart.data.datasets[1].data = relRet;
      retChart.update();
    }}
  }}
  if (defaultVid) updateRetentionChart(defaultVid);
}}

// Views distribution (horizontal bar of top 15)
const topVideos = funnelData.sort((a,b) => b.views - a.views).slice(0, 15);
new Chart(document.getElementById('viewsChart'), {{
  type: 'bar',
  data: {{
    labels: topVideos.map(d => d.title.substring(0, 30)),
    datasets: [{{
      label: 'Views',
      data: topVideos.map(d => d.views),
      backgroundColor: '#f0c040',
      borderRadius: 4,
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true,
    plugins: {{ title: {{ display: true, text: 'Top 15 Videos by Views', color: '#e0e0e0' }} }},
    scales: {{ x: {{ beginAtZero: true }} }}
  }}
}});

// Correlation chart
new Chart(document.getElementById('corrChart'), {{
  type: 'bar',
  data: {{
    labels: Object.keys(corrData),
    datasets: [{{
      label: 'Correlation with Views',
      data: Object.values(corrData),
      backgroundColor: Object.values(corrData).map(v => v > 0 ? '#2ed573' : '#ff4757'),
      borderRadius: 6,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ title: {{ display: true, text: 'Correlation with Views', color: '#e0e0e0' }} }},
    scales: {{ y: {{ beginAtZero: false }} }}
  }}
}});

// Trend chart
if (trendData.length > 0) {{
  new Chart(document.getElementById('trendChart'), {{
    type: 'line',
    data: {{
      labels: trendData.map(d => d.date.substring(0, 10)),
      datasets: [{{
        label: 'Watch Time (hours)',
        data: trendData.map(d => d.value),
        borderColor: '#ff6b35',
        backgroundColor: 'rgba(255,107,53,0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 3,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ title: {{ display: true, text: 'Weekly Watch Time Trend', color: '#e0e0e0' }} }},
      scales: {{ y: {{ beginAtZero: true }} }}
    }}
  }});
}}
</script>
</body>
</html>
'''.format(
    base_name=base.name,
    funnel_json=json.dumps(funnel_data),
    corr_json=json.dumps(correlations),
    trend_json=json.dumps(trend_data),
    content_type_json=content_type_json,
    traffic_json=traffic_json,
    search_json=search_json,
    demo_json=demo_json,
    retention_json=retention_json,
    geo_label_json=geo_label_json,
    geo_views_json=geo_views_json,
    device_label_json=device_label_json,
    device_views_json=device_views_json,
)

# ── Write HTML ──────────────────────────────────────────────────────
with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Report generated: {OUTPUT_HTML}")

# ── Serve or exit ───────────────────────────────────────────────────
if args.no_serve:
    print("Done. Open report.html in your browser.")
    sys.exit(0)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def log_message(self, fmt, *args):
        pass  # suppress logs

def serve():
    server = HTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/report.html"
    print(f"\nServer running at: {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.shutdown()

serve()
