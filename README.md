# YouTube Analytics Pipeline

Automated fetching and analysis of YouTube Studio data. No more manual CSV exports.

## What It Does

1. **Fetches** your YouTube analytics directly via the official YouTube Analytics API
2. **Saves** the data as CSVs matching your existing Studio export format
3. **Analyzes** the data to find what's working, what's not, and what to do next

## File Structure

```
.
├── scripts/
│   ├── fetch_youtube_data.py      # Pulls data from YouTube API
│   ├── youtube_analytics.py       # Runs the analysis report
│   ├── run_full_pipeline.py       # One-command: fetch + analyze
│   └── client_secret.json         # Your Google OAuth credentials (you create this)
│   └── token.pickle               # Auto-generated after first auth
├── data/
│   ├── api_fetch_2026-04-30_.../  # API-fetched data (auto-created)
│   │   ├── Table data.csv
│   │   ├── Chart data.csv
│   │   └── Totals.csv
│   └── latest/ -> symlink to most recent fetch
└── Content 2024-.../              # Manual exports (still supported)
```

---

## Setup (One-Time)

### 1. Install Dependencies

```bash
uv pip install pandas numpy google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### 2. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g., "youtube-analytics-fetcher")
3. Go to **APIs & Services → Library**
4. Enable these two APIs:
   - **YouTube Analytics API**
   - **YouTube Data API v3**
5. Go to **APIs & Services → Credentials**
6. Click **Create Credentials → OAuth client ID**
7. Choose **Desktop app** as the application type
8. Name it "YouTube Analytics Fetcher"
9. Click **Create**
10. Download the JSON file
11. Rename it to `client_secret.json` and move it to `scripts/client_secret.json`

### 3. First Run (Browser Auth)

```bash
uv run python scripts/fetch_youtube_data.py
```

This will open your browser for OAuth authentication. Log in with the Google account that owns your YouTube channel. Grant permission to view your YouTube analytics.

After authentication, a `token.pickle` file is saved in `scripts/`. This contains your refresh token — **future runs won't need browser auth**.

---

## Usage

### Option A: Fetch Only

```bash
uv run python scripts/fetch_youtube_data.py
```

This saves data to `data/api_fetch_<timestamp>/` and creates a `data/latest` symlink.

### Option B: Analyze Only (Existing Data)

```bash
# Analyze the most recent API fetch
uv run python scripts/youtube_analytics.py

# Analyze a specific directory
uv run python scripts/youtube_analytics.py --data-dir data/api_fetch_2026-04-30_120000

# Analyze manual Studio exports
uv run python scripts/youtube_analytics.py --data-dir "Content 2024-07-14_2026-04-30 Jorge Venegas Photo"
```

### Option C: Full Pipeline (Fetch + Analyze)

```bash
uv run python scripts/run_full_pipeline.py
```

---

## Automate With Cron (Weekly)

Run this every Sunday to keep your analytics fresh:

```bash
# Edit your crontab
crontab -e

# Add this line (runs every Sunday at 9 AM)
0 9 * * 0 cd /Users/jorge/code/yt-skills && /Users/jorge/.local/bin/uv run python scripts/run_full_pipeline.py >> data/pipeline.log 2>&1
```

Or run it manually whenever you want an updated report.

---

## What Data Gets Fetched

### Per-Video Summary (`Table data.csv`)
- Views, watch time, average view duration, average % viewed
- Likes, dislikes, comments, shares
- Subscribers gained/lost
- Impressions, CTR
- Unique viewers
- Video title, publish date, duration

### Daily Breakdown (`Chart data.csv`)
- Daily views and watch time per video

### Channel Totals (`Totals.csv`)
- Daily channel-level views, watch time, subscribers gained/lost

### What's NOT Available via API
Some Studio-only metrics can't be fetched:
- Community clip views/watch time
- Post subscribers
- End screen / card click data
- "Stayed to watch (%)" — use `averageViewPercentage` instead
- Some advanced retention curves

These are nice-to-have but not critical for the core analysis.

---

## Quota & Limits

- You get **10,000 quota units per day**
- Each report query costs ~1 unit
- Fetching all three reports for your channel uses ~3 units
- **You can run this hundreds of times per day without issues**

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'googleapiclient'"
```bash
uv pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### "ERROR: scripts/client_secret.json not found"
You skipped step 2. Download the OAuth credentials from Google Cloud Console and save as `scripts/client_secret.json`.

### "Token expired / Authentication error"
Delete `scripts/token.pickle` and re-run. It will go through browser auth again.

### "Access denied / Insufficient permissions"
Make sure you're logging in with the Google account that owns the YouTube channel. The API only works for channels you own/manage.

### Data looks different from Studio exports
The API returns the same underlying data but may have slight rounding differences. Watch time from API is in minutes (converted to hours in the script). Some metrics like "Stayed to watch" are Studio-only approximations.

---

## Next Steps

After running the pipeline:

1. Review the analysis output for content strategy insights
2. Use the recommendations to plan your next 3–5 videos
3. Re-run weekly to track progress
4. Consider storing historical data in a SQLite database if you want trend analysis over time
