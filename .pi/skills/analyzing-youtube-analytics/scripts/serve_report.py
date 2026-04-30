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

def classify_title(title):
    t = title.lower()
    if 'canon eos r' in t: return 'Canon EOS R'
    if 'canon' in t and 'eos' in t: return 'Canon EOS R'
    if 'fuji' in t or 'x100v' in t or 'x raw' in t: return 'Fujifilm'
    if 'dji' in t or 'osmo' in t or 'drone' in t or 'mini 4 pro' in t: return 'DJI'
    if 'insta360' in t: return 'Insta360'
    if 'olympus' in t or 'mju' in t: return 'Film/Olympus'
    if 'film' in t and 'loading' in t: return 'Film/Olympus'
    if 'tenba' in t or 'selphy' in t or 'retropia' in t or 'br-e1' in t: return 'Gear/Accessory'
    if 'food' in t or 'oreo' in t: return 'Food Photography'
    if 'street' in t or 'pov' in t or 'portland' in t:
        if 'setup' not in t and 'how to' not in t:
            return 'POV/Street'
    return 'Other'

def duration_bucket(d):
    if pd.isna(d): return 'Unknown'
    dm = d / 60
    if dm < 1: return '<1 min'
    if dm < 5: return '1-5 min'
    if dm < 10: return '5-10 min'
    return '10+ min'

def classify_format(title, duration):
    t = title.lower()
    if 'how to' in t or 'setup' in t or 'tutorial' in t: return 'Tutorial'
    if 'unboxing' in t: return 'Unboxing'
    if 'review' in t or 'in 2026' in t or 'in 2025' in t: return 'Review'
    if 'pov' in t or 'street photography' in t: return 'POV/Street'
    if 'food' in t: return 'Food Photo'
    if 'test' in t or 'experiment' in t: return 'Test/Experiment'
    if pd.notna(duration) and duration < 60: return 'Short/Gear'
    return 'Other'

summary['Topic'] = summary['Video title'].apply(classify_title)
summary['Duration bucket'] = summary['Duration (seconds)'].apply(duration_bucket)
summary['Format'] = summary.apply(lambda r: classify_format(r['Video title'], r['Duration (seconds)']), axis=1)

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
    "overall_ctr": safe_round((summary['Views'].sum() / summary['Impressions'].sum()) * 100, 2),
    "overall_like_rate": safe_round((summary['Likes'].sum() / summary['Views'].sum()) * 100, 2),
    "overall_engagement_rate": safe_round(((summary['Likes'].sum()+summary['Comments added'].sum()+summary['Shares'].sum()) / summary['Views'].sum()) * 100, 2),
    "videos_analyzed": len(summary),
}

# Top/bottom videos
top_cols = ['Video title', 'Views', 'Watch time (hours)', 'Likes', 'Comments added',
            'Shares', 'Net subscribers', 'CTR (%)', 'AVD ratio', 'Engagement rate (%)', 'Topic', 'Format']
top10 = summary.nlargest(10, 'Views')[top_cols]
bottom10 = summary.nsmallest(10, 'Views')[top_cols]

# Segment analysis
topic_agg = summary.groupby('Topic').agg({
    'Views': ['count', 'sum', 'mean', 'median'],
    'Watch time (hours)': 'sum',
    'Likes': 'sum',
    'Comments added': 'sum',
    'Shares': 'sum',
    'Net subscribers': 'sum',
    'CTR (%)': 'mean',
    'AVD ratio': 'mean',
    'Engagement rate (%)': 'mean',
    'Subscriber conversion rate (%)': 'mean',
    'Average percentage viewed (%)': 'mean',
}).round(2)
topic_agg.columns = ['Videos', 'Total Views', 'Avg Views', 'Median Views', 'Total WT',
                     'Total Likes', 'Total Comments', 'Total Shares', 'Net Subs',
                     'Avg CTR', 'Avg AVD', 'Avg Eng Rate', 'Avg Sub Conv', 'Avg % Viewed']
topic_agg = topic_agg.sort_values('Total Views', ascending=False).reset_index()

fmt_agg = summary.groupby('Format').agg({
    'Views': ['count', 'sum', 'mean', 'median'],
    'Watch time (hours)': 'sum',
    'Likes': 'sum',
    'Net subscribers': 'sum',
    'CTR (%)': 'mean',
    'AVD ratio': 'mean',
    'Engagement rate (%)': 'mean',
    'Subscriber conversion rate (%)': 'mean',
    'Average percentage viewed (%)': 'mean',
}).round(2)
fmt_agg.columns = ['Videos', 'Total Views', 'Avg Views', 'Median Views', 'Total WT',
                   'Total Likes', 'Net Subs', 'Avg CTR', 'Avg AVD', 'Avg Eng Rate',
                   'Avg Sub Conv', 'Avg % Viewed']
fmt_agg = fmt_agg.sort_values('Total Views', ascending=False).reset_index()

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
    "top_topics": top20['Topic'].value_counts().to_dict(),
    "bottom_topics": bottom20['Topic'].value_counts().to_dict(),
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
        "topic": row['Topic'],
        "format": row['Format'],
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
    <div class="kpi"><div class="value">{channel_snapshot['overall_ctr']:.2f}%</div><div class="label">Overall CTR</div></div>
    <div class="kpi"><div class="value">{channel_snapshot['overall_engagement_rate']:.2f}%</div><div class="label">Engagement Rate</div></div>
    <div class="kpi"><div class="value">{channel_snapshot['videos_analyzed']}</div><div class="label">Videos</div></div>
  </div>
</section>

<section>
  <h2>Performance Charts</h2>
  <div class="chart-row">
    <div class="chart-container">
      <canvas id="topicChart"></canvas>
    </div>
    <div class="chart-container">
      <canvas id="formatChart"></canvas>
    </div>
  </div>
  <div class="chart-row">
    <div class="chart-container">
      <canvas id="viewsChart"></canvas>
    </div>
    <div class="chart-container">
      <canvas id="corrChart"></canvas>
    </div>
  </div>
  {'<div class="chart-container"><canvas id="trendChart"></canvas></div>' if trend_data else ''}
</section>

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
        <th>Topic / Format</th>
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
        <td><span class="topic-tag">{row['Topic']} / {row['Format']}</span></td>
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
        <th>Topic / Format</th>
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
        <td><span class="topic-tag">{row['Topic']} / {row['Format']}</span></td>
      </tr>
'''

html += '''    </tbody>
  </table>
</section>

<section>
  <h2>Segment Analysis: By Topic</h2>
  <table>
    <thead>
      <tr>
        <th>Topic</th>
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

for _, row in topic_agg.iterrows():
    html += f'''      <tr>
        <td>{row['Topic']}</td>
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

html += '''    </tbody>
  </table>

  <h2>Segment Analysis: By Format</h2>
  <table>
    <thead>
      <tr>
        <th>Format</th>
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

for _, row in fmt_agg.iterrows():
    html += f'''      <tr>
        <td>{row['Format']}</td>
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

html += '''    </tbody>
  </table>

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

html += '''    </tbody>
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
        <th>Topic / Format</th>
      </tr>
    </thead>
    <tbody>
'''.format(top_vs_bottom=top_vs_bottom)

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
        <td><span class="topic-tag">{v['topic']} / {v['format']}</span></td>
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
    <thead><tr><th>Video</th><th class="num">Views</th><th class="num">Age (days)</th><th class="num">Views/Day</th><th>Topic</th></tr></thead>
    <tbody>
'''

for _, row in momentum.iterrows():
    html += f'''      <tr class="video-row">
        <td title="{row['Video title']}">{row['Video title'][:55]}</td>
        <td class="num">{int(row['Views']):,}</td>
        <td class="num">{int(row['Days since publish'])}</td>
        <td class="num">{safe_round(row['Views per day'], 1)}</td>
        <td><span class="topic-tag">{row['Topic']}</span></td>
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
const topicData = {topic_json};
const formatData = {format_json};
const funnelData = {funnel_json};
const corrData = {corr_json};
const trendData = {trend_json};

Chart.defaults.color = '#8888aa';
Chart.defaults.borderColor = '#2a2a4a';

// Topic views bar chart
new Chart(document.getElementById('topicChart'), {{
  type: 'bar',
  data: {{
    labels: topicData.map(d => d.Topic),
    datasets: [{{
      label: 'Total Views',
      data: topicData.map(d => d['Total Views']),
      backgroundColor: '#ff6b35',
      borderRadius: 6,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ title: {{ display: true, text: 'Views by Topic', color: '#e0e0e0' }} }},
    scales: {{ y: {{ beginAtZero: true }} }}
  }}
}});

// Format views bar chart
new Chart(document.getElementById('formatChart'), {{
  type: 'bar',
  data: {{
    labels: formatData.map(d => d.Format),
    datasets: [{{
      label: 'Total Views',
      data: formatData.map(d => d['Total Views']),
      backgroundColor: '#00d4aa',
      borderRadius: 6,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ title: {{ display: true, text: 'Views by Format', color: '#e0e0e0' }} }},
    scales: {{ y: {{ beginAtZero: true }} }}
  }}
}});

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
    topic_json=json.dumps(df_to_records(topic_agg)),
    format_json=json.dumps(df_to_records(fmt_agg)),
    funnel_json=json.dumps(funnel_data),
    corr_json=json.dumps(correlations),
    trend_json=json.dumps(trend_data),
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
