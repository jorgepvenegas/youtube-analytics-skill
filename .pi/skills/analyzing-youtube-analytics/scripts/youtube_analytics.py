#!/usr/bin/env python3
"""
YouTube Analytics Analysis Script
Supports both API-fetched data and manually exported Studio CSVs.

Usage:
    # Analyze latest API-fetched data
    uv run python scripts/youtube_analytics.py

    # Analyze a specific directory
    uv run python scripts/youtube_analytics.py --data-dir data/api_fetch_2026-04-30_120000

    # Analyze manually exported data
    uv run python scripts/youtube_analytics.py --data-dir "Content 2024-07-14_2026-04-30 Jorge Venegas Photo"
"""

import argparse
import pandas as pd
import numpy as np
from pathlib import Path

# ── Argument parsing ────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Analyze YouTube Analytics data")
parser.add_argument(
    "--data-dir",
    type=str,
    default=None,
    help="Directory containing Table data.csv, Chart data.csv, and Totals.csv",
)
args = parser.parse_args()

PROJECT_ROOT = Path.cwd()

# Auto-resolve data directory
if args.data_dir:
    base = PROJECT_ROOT / args.data_dir
else:
    # Try latest symlink first, then fall back to manual export
    latest = PROJECT_ROOT / "data" / "latest"
    if latest.exists():
        base = latest.resolve()
    else:
        # Fall back to the manual export directory
        candidates = list(PROJECT_ROOT.glob("Content*"))
        if candidates:
            base = sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]
        else:
            print("ERROR: No data directory found.")
            print("Run: uv run python scripts/fetch_youtube_data.py")
            print("Or:  uv run python scripts/youtube_analytics.py --data-dir <path>")
            exit(1)

print(f"Analyzing data from: {base}")

# ── Load data ───────────────────────────────────────────────────────
summary = pd.read_csv(base / "Table data.csv")

# Clean summary data — remove the Total row
summary = summary[summary['Content'] != 'Total'].copy()

# Numeric columns
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

# Parse average view duration
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

# Engagement metrics
summary['Like rate (%)'] = (summary['Likes'] / summary['Views']) * 100
summary['Comment rate (%)'] = (summary['Comments added'] / summary['Views']) * 100
summary['Share rate (%)'] = (summary['Shares'] / summary['Views']) * 100
summary['Engagement rate (%)'] = ((summary['Likes'] + summary['Comments added'] + summary['Shares']) / summary['Views']) * 100
summary['Dislike rate (%)'] = (summary['Dislikes'] / summary['Views']) * 100
summary['Net subscribers'] = summary['Subscribers gained'] - summary['Subscribers lost']
summary['Subscriber conversion rate (%)'] = (summary['Net subscribers'] / summary['Views']) * 100
summary['CTR (%)'] = summary['Impressions click-through rate (%)']

# Parse publish date
summary['Video publish time'] = pd.to_datetime(summary['Video publish time'], format='%b %d, %Y', errors='coerce')
summary['Days since publish'] = (pd.Timestamp('2026-04-30') - summary['Video publish time']).dt.days

# Topic classification
def classify_title(title):
    t = title.lower()
    if 'canon eos r' in t:
        return 'Canon EOS R'
    if 'canon' in t and 'eos' in t:
        return 'Canon EOS R'
    if 'fuji' in t or 'x100v' in t or 'x raw' in t:
        return 'Fujifilm'
    if 'dji' in t or 'osmo' in t or 'drone' in t or 'mini 4 pro' in t:
        return 'DJI'
    if 'insta360' in t:
        return 'Insta360'
    if 'olympus' in t or 'mju' in t:
        return 'Film/Olympus'
    if 'film' in t and 'loading' in t:
        return 'Film/Olympus'
    if 'tenba' in t or 'selphy' in t or 'retropia' in t or 'br-e1' in t:
        return 'Gear/Accessory'
    if 'food' in t or 'oreo' in t:
        return 'Food Photography'
    if 'street' in t or 'pov' in t or 'portland' in t:
        if 'setup' not in t and 'how to' not in t:
            return 'POV/Street'
    return 'Other'

summary['Topic'] = summary['Video title'].apply(classify_title)

# Duration buckets
def duration_bucket(d):
    if pd.isna(d): return 'Unknown'
    dm = d / 60
    if dm < 1: return '<1 min'
    if dm < 5: return '1-5 min'
    if dm < 10: return '5-10 min'
    return '10+ min'

summary['Duration bucket'] = summary['Duration (seconds)'].apply(duration_bucket)

# Format classification
def classify_format(title, duration):
    t = title.lower()
    if 'how to' in t or 'setup' in t or 'tutorial' in t:
        return 'Tutorial'
    if 'unboxing' in t:
        return 'Unboxing'
    if 'review' in t or 'in 2026' in t or 'in 2025' in t:
        return 'Review'
    if 'pov' in t or 'street photography' in t:
        return 'POV/Street'
    if 'food' in t:
        return 'Food Photo'
    if 'test' in t or 'experiment' in t:
        return 'Test/Experiment'
    if pd.notna(duration) and duration < 60:
        return 'Short/Gear'
    return 'Other'

summary['Format'] = summary.apply(lambda r: classify_format(r['Video title'], r['Duration (seconds)']), axis=1)

# ============================ REPORT ============================
print("=" * 70)
print("YOUTUBE LIFETIME ANALYTICS REPORT: Jorge Venegas Photo")
print(f"Data source: {base.name}")
print("=" * 70)

print("\n--- CHANNEL SNAPSHOT ---")
print(f"Total lifetime views:     {summary['Views'].sum():>10,.0f}")
print(f"Total watch time:         {summary['Watch time (hours)'].sum():>10,.1f} hours")
print(f"Total subscribers gained: {summary['Subscribers gained'].sum():>10,.0f}")
print(f"Total subscribers lost:   {summary['Subscribers lost'].sum():>10,.0f}")
print(f"Net subscriber change:    {summary['Net subscribers'].sum():>10,.0f}")
print(f"Total likes:              {summary['Likes'].sum():>10,.0f}")
print(f"Total comments:           {summary['Comments added'].sum():>10,.0f}")
print(f"Total shares:             {summary['Shares'].sum():>10,.0f}")
print(f"Total impressions:        {summary['Impressions'].sum():>10,.0f}")
print(f"Overall CTR:              {(summary['Views'].sum() / summary['Impressions'].sum()) * 100:>10.2f}%")
print(f"Overall like rate:        {(summary['Likes'].sum() / summary['Views'].sum()) * 100:>10.2f}%")
print(f"Overall engagement rate:  {((summary['Likes'].sum()+summary['Comments added'].sum()+summary['Shares'].sum()) / summary['Views'].sum()) * 100:>10.2f}%")
print(f"Videos analyzed:          {len(summary):>10,}")

print("\n--- TOP 10 VIDEOS BY VIEWS ---")
top_cols = ['Video title', 'Views', 'Watch time (hours)', 'Likes', 'Comments added',
            'Shares', 'Net subscribers', 'CTR (%)', 'AVD ratio', 'Engagement rate (%)', 'Topic', 'Format']
top10 = summary.nlargest(10, 'Views')[top_cols]
for idx, row in top10.iterrows():
    print(f"  {row['Video title'][:50]:50s} | Views: {row['Views']:>6,.0f} | CTR: {row['CTR (%)']:>5.2f}% | AVD: {row['AVD ratio']:>4.2f} | Eng: {row['Engagement rate (%)']:>4.2f}% | Subs: {row['Net subscribers']:>+3.0f} | {row['Topic']}/{row['Format']}")

print("\n--- BOTTOM 10 VIDEOS BY VIEWS ---")
bottom10 = summary.nsmallest(10, 'Views')[top_cols]
for idx, row in bottom10.iterrows():
    print(f"  {row['Video title'][:50]:50s} | Views: {row['Views']:>6,.0f} | CTR: {row['CTR (%)']:>5.2f}% | AVD: {row['AVD ratio']:>4.2f} | Eng: {row['Engagement rate (%)']:>4.2f}% | Subs: {row['Net subscribers']:>+3.0f} | {row['Topic']}/{row['Format']}")

print("\n--- SEGMENT ANALYSIS BY TOPIC ---")
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
print(topic_agg.sort_values('Total Views', ascending=False).to_string())

print("\n--- SEGMENT ANALYSIS BY FORMAT ---")
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
print(fmt_agg.sort_values('Total Views', ascending=False).to_string())

print("\n--- SEGMENT ANALYSIS BY DURATION BUCKET ---")
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
print(dur_agg.sort_values('Total Views', ascending=False).to_string())

print("\n--- CORRELATION INSIGHTS (vs Views) ---")
corr_cols = ['Views', 'CTR (%)', 'AVD ratio', 'Engagement rate (%)',
             'Subscriber conversion rate (%)', 'Like rate (%)', 'Comment rate (%)',
             'Share rate (%)', 'Average percentage viewed (%)',
             'Watch time per view (minutes)']
available_corr_cols = [c for c in corr_cols if c in summary.columns]
corr = summary[available_corr_cols].corr()['Views'].drop('Views').sort_values(ascending=False)
print(corr.round(2).to_string())

print("\n--- TOP 20% vs BOTTOM 20% ---")
top20 = summary.nlargest(max(1, int(len(summary) * 0.2)), 'Views')
bottom20 = summary.nsmallest(max(1, int(len(summary) * 0.2)), 'Views')
print(f"Top 20% ({len(top20)} videos) vs Bottom 20% ({len(bottom20)} videos)")
print(f"Avg views:     {top20['Views'].mean():>8,.0f} vs {bottom20['Views'].mean():>8,.0f} ({top20['Views'].mean()/bottom20['Views'].mean():.0f}x)")
print(f"Avg CTR:       {top20['CTR (%)'].mean():>8.2f}% vs {bottom20['CTR (%)'].mean():>8.2f}%")
print(f"Avg AVD:       {top20['AVD ratio'].mean():>8.2f} vs {bottom20['AVD ratio'].mean():>8.2f}")
print(f"Avg Eng rate:  {top20['Engagement rate (%)'].mean():>8.2f}% vs {bottom20['Engagement rate (%)'].mean():>8.2f}%")
print(f"Avg Sub conv:  {top20['Subscriber conversion rate (%)'].mean():>8.3f}% vs {bottom20['Subscriber conversion rate (%)'].mean():>8.3f}%")
avg_pct_top = top20['Average percentage viewed (%)'].mean()
avg_pct_bot = bottom20['Average percentage viewed (%)'].mean()
if pd.notna(avg_pct_top) and pd.notna(avg_pct_bot):
    print(f"Avg % viewed:  {avg_pct_top:>8.1f}% vs {avg_pct_bot:>8.1f}%")
print(f"Top topics:    {top20['Topic'].value_counts().to_dict()}")
print(f"Bottom topics: {bottom20['Topic'].value_counts().to_dict()}")

print("\n--- ENGAGEMENT DEEP DIVE ---")
print("Videos with highest engagement rate (min 100 views):")
eng_filter = summary[summary['Views'] >= 100].nlargest(5, 'Engagement rate (%)')
for idx, row in eng_filter.iterrows():
    print(f"  {row['Video title'][:50]:50s} | Views: {row['Views']:>6,.0f} | Likes: {row['Likes']:>3,.0f} | Comments: {row['Comments added']:>2,.0f} | Shares: {row['Shares']:>2,.0f} | Eng: {row['Engagement rate (%)']:>4.2f}%")

print("\nVideos with highest like rate (min 100 views):")
like_filter = summary[summary['Views'] >= 100].nlargest(5, 'Like rate (%)')
for idx, row in like_filter.iterrows():
    print(f"  {row['Video title'][:50]:50s} | Views: {row['Views']:>6,.0f} | Likes: {row['Likes']:>3,.0f} | Like rate: {row['Like rate (%)']:>4.2f}%")

print("\n--- SUBSCRIBER CONVERSION DEEP DIVE ---")
print("Videos with best subscriber conversion (min 100 views):")
sub_filter = summary[summary['Views'] >= 100].nlargest(5, 'Subscriber conversion rate (%)')
for idx, row in sub_filter.iterrows():
    print(f"  {row['Video title'][:50]:50s} | Views: {row['Views']:>6,.0f} | Gained: {row['Subscribers gained']:>2,.0f} | Lost: {row['Subscribers lost']:>2,.0f} | Net: {row['Net subscribers']:>+3.0f} | Conv: {row['Subscriber conversion rate (%)']:>5.3f}%")

print("\n--- FUNNEL DIAGNOSIS PER VIDEO ---")
print(f"{'Video':50s} | {'Views':>7s} | {'CTR':>5s} | {'%Viewed':>7s} | {'Discovery':>10s} | {'Retention':>10s}")
print("-" * 95)
for idx, row in summary.iterrows():
    ctr = row['CTR (%)']
    pct = row['Average percentage viewed (%)']
    views = row['Views']
    title = row['Video title'][:48]

    disc = "Strong" if pd.notna(ctr) and ctr >= 8 else ("Weak" if pd.notna(ctr) and ctr < 5 else "Moderate")
    ret = "Strong" if pd.notna(pct) and pct >= 70 else ("Weak" if pd.notna(pct) and pct < 40 else "Moderate")

    print(f"  {title:48s} | {views:>7,.0f} | {ctr:>5.1f} | {pct:>7.1f} | {disc:>10s} | {ret:>10s}")

print("\n--- VIEWS NORMALIZED BY AGE (views per day since publish) ---")
summary['Views per day'] = summary['Views'] / summary['Days since publish'].clip(lower=1)
print("Top 5 by views per day (momentum):")
momentum = summary.nlargest(5, 'Views per day')[['Video title', 'Views', 'Days since publish', 'Views per day', 'Topic']]
for idx, row in momentum.iterrows():
    print(f"  {row['Video title'][:50]:50s} | Age: {row['Days since publish']:>3,.0f}d | {row['Views per day']:>6.1f} views/day | {row['Topic']}")

# Weekly channel growth trend from Totals.csv if available
totals_path = base / "Totals.csv"
if totals_path.exists():
    print("\n--- WEEKLY CHANNEL GROWTH TREND ---")
    totals = pd.read_csv(totals_path)
    totals['Date'] = pd.to_datetime(totals['Date'])
    totals = totals.sort_values('Date')

    # Try to find a watch time column
    wt_col = None
    for c in ['Watch time (hours)', 'YouTube Premium watch time (hours)', 'estimatedMinutesWatched']:
        if c in totals.columns:
            wt_col = c
            break

    if wt_col:
        print(f"First week WT: {totals[wt_col].iloc[0]:.2f}")
        print(f"Last week WT:  {totals[wt_col].iloc[-1]:.2f}")
        print(f"Peak week WT:  {totals[wt_col].max():.2f} on {totals.loc[totals[wt_col].idxmax(), 'Date'].strftime('%Y-%m-%d')}")

        n = min(12, len(totals) // 2)
        if n > 0:
            recent = totals.tail(n)[wt_col].mean()
            early = totals.head(n)[wt_col].mean()
            if early > 0:
                print(f"Early avg (first {n}): {early:.2f} | Recent avg (last {n}): {recent:.2f} | Growth: {recent/early:.1f}x")

print("\n" + "=" * 70)
print("END OF REPORT")
print("=" * 70)
