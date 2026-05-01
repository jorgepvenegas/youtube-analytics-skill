#!/usr/bin/env python3
"""
Fetch YouTube Analytics data via API and save as CSVs.
Run this weekly to keep your analytics data fresh.

Setup:
1. Go to https://console.cloud.google.com/
2. Create a project → Enable "YouTube Analytics API" and "YouTube Data API v3"
3. Create OAuth 2.0 credentials (Desktop app)
4. Download client_secret.json and save it as scripts/client_secret.json
5. Run this script once to authenticate (opens browser)
6. After that, it runs headless using the saved token

Usage:
    uv run python scripts/fetch_youtube_data.py
"""

import os
import sys
import json
import pickle
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

import pandas as pd

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ── Config ──────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = Path.cwd()
DATA_DIR = PROJECT_ROOT / "data"
TOKEN_PATH = SCRIPT_DIR / "token.pickle"
CLIENT_SECRET_PATH = SCRIPT_DIR / "client_secret.json"
WT_MINUTES_TO_HOURS = 1 / 60


# ── Auth ────────────────────────────────────────────────────────────
def get_credentials():
    creds = None
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing access token...")
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_PATH.exists():
                print(f"ERROR: {CLIENT_SECRET_PATH} not found.")
                sys.exit(1)
            print("Starting OAuth flow (browser will open)...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "wb") as token:
            pickle.dump(creds, token)
        print(f"Token saved to {TOKEN_PATH}")

    return creds


def get_channel_id(youtube):
    response = youtube.channels().list(part="id", mine=True).execute()
    return response["items"][0]["id"]


# ── API Helpers ─────────────────────────────────────────────────────
def safe_api_call(func, max_retries=3):
    import time
    for attempt in range(max_retries):
        try:
            return func().execute()
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise


def fetch_report(analytics, dimensions, metrics, start_date, end_date,
                 filters=None, sort=None, max_results=None):
    all_rows = []
    page_token = None

    while True:
        kwargs = {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "metrics": ",".join(metrics),
            "dimensions": ",".join(dimensions),
        }
        if filters:
            kwargs["filters"] = filters
        if sort:
            kwargs["sort"] = sort
        if max_results:
            kwargs["maxResults"] = max_results
        if page_token:
            kwargs["pageToken"] = page_token

        response = safe_api_call(lambda: analytics.reports().query(**kwargs))
        rows = response.get("rows", [])
        all_rows.extend(rows)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    headers = [h["name"] for h in response.get("columnHeaders", [])]
    return all_rows, headers


# ── Data Fetchers ───────────────────────────────────────────────────
def fetch_video_list(youtube, channel_id):
    videos = []
    page_token = None

    while True:
        kwargs = {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "maxResults": 50,
            "order": "date",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = safe_api_call(lambda: youtube.search().list(**kwargs))
        for item in response.get("items", []):
            if item["id"]["kind"] == "youtube#video":
                videos.append({
                    "video_id": item["id"]["videoId"],
                    "title": item["snippet"]["title"],
                    "published_at": item["snippet"]["publishedAt"],
                })

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    # Fetch durations via videos().list (contentDetails)
    video_ids = [v["video_id"] for v in videos]
    durations = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        resp = safe_api_call(lambda: youtube.videos().list(
            part="contentDetails", id=",".join(batch)
        ))
        for item in resp.get("items", []):
            durations[item["id"]] = iso_duration_to_seconds(
                item.get("contentDetails", {}).get("duration", "PT0S")
            )

    for v in videos:
        v["duration_sec"] = durations.get(v["video_id"], 0)

    return pd.DataFrame(videos)


def iso_duration_to_seconds(iso):
    import re
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso)
    if not match:
        return 0
    h, m, s = match.groups()
    return int(h or 0) * 3600 + int(m or 0) * 60 + int(s or 0)


def fetch_video_analytics(analytics, video_ids, start_date, end_date):
    """Fetch per-video lifetime summary metrics using video ID filters."""
    vid_filter = ",".join(video_ids)

    # Call 1: Views + watch time + retention + subs
    rows1, h1 = fetch_report(
        analytics, dimensions=["video"],
        metrics=["views", "estimatedMinutesWatched", "averageViewDuration",
                 "averageViewPercentage", "subscribersGained", "subscribersLost"],
        start_date=start_date, end_date=end_date,
        filters=f"video=={vid_filter}",
    )
    df1 = pd.DataFrame(rows1, columns=h1)
    df1.columns = ["Content", "Views", "estimatedMinutesWatched", "averageViewDuration",
                   "averageViewPercentage", "subscribersGained", "subscribersLost"]

    # Call 2: Engagement
    rows2, h2 = fetch_report(
        analytics, dimensions=["video"],
        metrics=["views", "likes", "comments", "shares"],
        start_date=start_date, end_date=end_date,
        filters=f"video=={vid_filter}",
    )
    df2 = pd.DataFrame(rows2, columns=h2)
    df2.columns = ["Content", "Views_eng", "likes", "comments", "shares"]
    df2 = df2[["Content", "likes", "comments", "shares"]]

    # Merge
    df = df1.merge(df2, on="Content", how="left")
    df["Watch time (hours)"] = df["estimatedMinutesWatched"] * WT_MINUTES_TO_HOURS
    df["Avg view duration (seconds)"] = df["averageViewDuration"]
    df["Avg view duration"] = pd.to_datetime(df["averageViewDuration"], unit="s").dt.strftime("%H:%M:%S")
    df["dislikes"] = 0
    return df


def fetch_daily_video_breakdown(analytics, video_ids, start_date, end_date):
    vid_filter = ",".join(video_ids)
    rows, headers = fetch_report(
        analytics, dimensions=["day", "video"],
        metrics=["views", "estimatedMinutesWatched"],
        start_date=start_date, end_date=end_date,
        filters=f"video=={vid_filter}",
    )
    df = pd.DataFrame(rows, columns=headers)
    df.columns = ["Date", "Content", "Views", "estimatedMinutesWatched"]
    df["Watch time (hours)"] = df["estimatedMinutesWatched"] * WT_MINUTES_TO_HOURS
    return df


def fetch_channel_totals(analytics, start_date, end_date):
    rows, headers = fetch_report(
        analytics, dimensions=["day"],
        metrics=["views", "estimatedMinutesWatched", "subscribersGained", "subscribersLost"],
        start_date=start_date, end_date=end_date,
    )
    df = pd.DataFrame(rows, columns=headers)
    df.columns = ["Date", "Views", "estimatedMinutesWatched", "subscribersGained", "subscribersLost"]
    df["Watch time (hours)"] = df["estimatedMinutesWatched"] * WT_MINUTES_TO_HOURS
    return df


def fetch_traffic_sources(analytics, video_ids, start_date, end_date, video_df):
    """Fetch per-video traffic source breakdown."""
    vid_filter = ",".join(video_ids)

    rows, headers = fetch_report(
        analytics,
        dimensions=["video", "insightTrafficSourceType"],
        metrics=["views", "estimatedMinutesWatched"],
        start_date=start_date,
        end_date=end_date,
        filters=f"video=={vid_filter}",
    )

    df = pd.DataFrame(rows, columns=headers)
    if df.empty:
        return pd.DataFrame(columns=["Video", "Video title", "Traffic source", "Views", "Watch time (hours)"])

    df.columns = ["Video", "Traffic source", "Views", "estimatedMinutesWatched"]

    # Join video titles
    title_map = video_df.set_index("video_id")["title"]
    df["Video title"] = df["Video"].map(title_map)

    # Convert watch time to hours
    df["Watch time (hours)"] = (df["estimatedMinutesWatched"] * WT_MINUTES_TO_HOURS).round(4)

    # Clean up types
    df["Views"] = df["Views"].astype(int)

    # Select and order final columns
    df = df[["Video", "Video title", "Traffic source", "Views", "Watch time (hours)"]]

    return df


def fetch_search_terms(analytics, video_ids, start_date, end_date, video_df):
    """Fetch top search terms that drive traffic to each video."""
    vid_filter = ",".join(video_ids)

    rows, headers = fetch_report(
        analytics,
        dimensions=["video", "insightTrafficSourceDetail"],
        metrics=["views", "estimatedMinutesWatched"],
        start_date=start_date,
        end_date=end_date,
        filters=f"video=={vid_filter};insightTrafficSourceType==YT_SEARCH",
        sort="-views",
        max_results=25,
    )

    df = pd.DataFrame(rows, columns=headers)
    if df.empty:
        return pd.DataFrame(columns=["Video", "Video title", "Search term", "Views", "Watch time (hours)"])

    df.columns = ["Video", "Search term", "Views", "estimatedMinutesWatched"]

    # Join video titles
    title_map = video_df.set_index("video_id")["title"]
    df["Video title"] = df["Video"].map(title_map)

    # Convert watch time to hours
    df["Watch time (hours)"] = (df["estimatedMinutesWatched"] * WT_MINUTES_TO_HOURS).round(4)

    # Clean up types
    df["Views"] = df["Views"].astype(int)

    # Select and order final columns
    df = df[["Video", "Video title", "Search term", "Views", "Watch time (hours)"]]

    return df


# ── Main ────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("YouTube Analytics API Fetcher")
    print("=" * 60)

    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    analytics = build("youtubeAnalytics", "v2", credentials=creds)

    channel_id = get_channel_id(youtube)
    print(f"Authenticated. Channel ID: {channel_id}")

    start_date = "2020-01-01"
    end_date = datetime.now().strftime("%Y-%m-%d")
    print(f"\nFetching data from {start_date} to {end_date}...")

    DATA_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir = DATA_DIR / f"api_fetch_{timestamp}"
    output_dir.mkdir(exist_ok=True)
    print(f"Output directory: {output_dir}")

    # ── Fetch video list ──
    print("\n[1/6] Fetching video list...")
    video_df = fetch_video_list(youtube, channel_id)
    video_ids = video_df["video_id"].tolist()
    print(f"      Found {len(video_df)} videos")

    # ── Fetch per-video analytics ──
    print("\n[2/6] Fetching per-video lifetime analytics...")
    video_stats = fetch_video_analytics(analytics, video_ids, start_date, end_date)
    print(f"      Fetched stats for {len(video_stats)} videos")

    # Merge with video metadata
    video_stats = video_stats.merge(
        video_df, left_on="Content", right_on="video_id", how="left"
    )

    # Build Table data.csv
    table_data = pd.DataFrame()
    table_data["Content"] = video_stats["Content"]
    table_data["Video title"] = video_stats["title"]
    table_data["Video publish time"] = pd.to_datetime(video_stats["published_at"]).dt.strftime("%b %d, %Y")
    table_data["Duration"] = video_stats["duration_sec"]
    table_data["Views"] = video_stats["Views"].astype(int)
    table_data["Watch time (hours)"] = video_stats["Watch time (hours)"].round(4)
    table_data["Subscribers gained"] = video_stats["subscribersGained"].astype(int)
    table_data["Subscribers lost"] = video_stats["subscribersLost"].astype(int)
    table_data["Net subscribers"] = (video_stats["subscribersGained"] - video_stats["subscribersLost"]).astype(int)
    table_data["Likes"] = video_stats["likes"].astype(int)
    table_data["Dislikes"] = video_stats["dislikes"].astype(int)
    table_data["Comments added"] = video_stats["comments"].astype(int)
    table_data["Shares"] = video_stats["shares"].astype(int)
    table_data["Impressions"] = 0
    table_data["Impressions click-through rate (%)"] = 0.0
    table_data["Average view duration"] = video_stats["Avg view duration"]
    table_data["Average percentage viewed (%)"] = video_stats["averageViewPercentage"].round(2)

    table_data = table_data.sort_values("Views", ascending=False)

    total_row = pd.DataFrame([{
        "Content": "Total",
        "Video title": "",
        "Video publish time": "",
        "Duration": "",
        "Views": table_data["Views"].sum(),
        "Watch time (hours)": table_data["Watch time (hours)"].sum(),
        "Subscribers gained": table_data["Subscribers gained"].sum(),
        "Subscribers lost": table_data["Subscribers lost"].sum(),
        "Net subscribers": table_data["Net subscribers"].sum(),
        "Likes": table_data["Likes"].sum(),
        "Dislikes": table_data["Dislikes"].sum(),
        "Comments added": table_data["Comments added"].sum(),
        "Shares": table_data["Shares"].sum(),
        "Impressions": table_data["Impressions"].sum(),
        "Impressions click-through rate (%)": 0.0,
        "Average view duration": "",
        "Average percentage viewed (%)": "",
    }])
    table_data = pd.concat([table_data, total_row], ignore_index=True)

    table_path = output_dir / "Table data.csv"
    table_data.to_csv(table_path, index=False)
    print(f"      Saved: {table_path}")

    # ── Fetch daily video breakdown ──
    print("\n[3/6] Fetching daily video breakdown...")
    daily_df = fetch_daily_video_breakdown(analytics, video_ids, start_date, end_date)
    print(f"      Fetched {len(daily_df)} day-video records")

    daily_df = daily_df.merge(
        video_df[["video_id", "title", "published_at", "duration_sec"]],
        left_on="Content", right_on="video_id", how="left"
    )

    chart_data = pd.DataFrame()
    chart_data["Date"] = daily_df["Date"]
    chart_data["Content"] = daily_df["Content"]
    chart_data["Video title"] = daily_df["title"]
    chart_data["Video publish time"] = pd.to_datetime(daily_df["published_at"]).dt.strftime("%b %d, %Y")
    chart_data["Duration"] = daily_df["duration_sec"]
    chart_data["Views"] = daily_df["Views"].astype(int)
    chart_data["Watch time (hours)"] = daily_df["Watch time (hours)"].round(4)

    chart_path = output_dir / "Chart data.csv"
    chart_data.to_csv(chart_path, index=False)
    print(f"      Saved: {chart_path}")

    # ── Fetch channel totals ──
    print("\n[4/6] Fetching channel daily totals...")
    totals_df = fetch_channel_totals(analytics, start_date, end_date)
    print(f"      Fetched {len(totals_df)} daily records")

    totals_out = pd.DataFrame()
    totals_out["Date"] = totals_df["Date"]
    totals_out["Views"] = totals_df["Views"].astype(int)
    totals_out["Watch time (hours)"] = totals_df["Watch time (hours)"].round(4)
    totals_out["Subscribers gained"] = totals_df["subscribersGained"].astype(int)
    totals_out["Subscribers lost"] = totals_df["subscribersLost"].astype(int)

    totals_path = output_dir / "Totals.csv"
    totals_out.to_csv(totals_path, index=False)
    print(f"      Saved: {totals_path}")

    # ── Fetch traffic sources ──
    print("\n[5/6] Fetching traffic sources...")
    traffic_df = fetch_traffic_sources(analytics, video_ids, start_date, end_date, video_df)
    print(f"      Fetched {len(traffic_df)} traffic source records")

    traffic_path = output_dir / "Traffic sources.csv"
    traffic_df.to_csv(traffic_path, index=False)
    print(f"      Saved: {traffic_path}")

    # ── Fetch search terms ──
    print("\n[6/6] Fetching search terms...")
    search_df = fetch_search_terms(analytics, video_ids, start_date, end_date, video_df)
    print(f"      Fetched {len(search_df)} search term records")

    search_path = output_dir / "Search terms.csv"
    search_df.to_csv(search_path, index=False)
    print(f"      Saved: {search_path}")

    # ── Summary ──
    print("\n" + "=" * 60)
    print("FETCH COMPLETE")
    print("=" * 60)
    print(f"\nFiles saved to: {output_dir}")

    latest_link = DATA_DIR / "latest"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(output_dir, target_is_directory=True)
    print(f"Symlink created: data/latest -> {output_dir}")


if __name__ == "__main__":
    main()
