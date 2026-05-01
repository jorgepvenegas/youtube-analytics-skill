# Data Preparation

Guide for loading, cleaning, and merging YouTube Studio data — via automated API fetch or manual CSV exports.

---

## Automated API Fetch (Recommended)

The `scripts/fetch_youtube_data.py` script pulls data directly from the YouTube Analytics API. No manual exports needed after initial setup.

### One-Time Setup

1. **Google Cloud Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project (e.g., `youtube-analytics-fetcher`)
   - Enable **YouTube Analytics API** and **YouTube Data API v3**

2. **OAuth Consent Screen**
   - Go to **APIs & Services → OAuth consent screen**
   - Set **User Type** to **External**
   - Fill in app name and support email
   - Under **Test users**, add your Google account email
   - Save

3. **Create Credentials**
   - Go to **Credentials → Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Desktop app**
   - Download the JSON file
   - Rename to `client_secret.json` and save in `scripts/`

4. **Install Dependencies**
   ```bash
   uv pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
   ```

5. **First Run (Browser Auth)**
   ```bash
   uv run python scripts/fetch_youtube_data.py
   ```
   - Browser opens for OAuth
   - Sign in with the Google account that owns your YouTube channel
   - Grant permission to view analytics
   - A `token.pickle` file is saved — future runs use this (no browser needed)

   **Troubleshooting:**
   - If you see "Access blocked: YT Metrics can only be used within its organization" — your OAuth app is set to **Internal**. Change it to **External** on the OAuth consent screen.
   - If you see "Error 403: access_denied" — add your email to **Test users** on the OAuth consent screen.
   - If you see "App is not verified" — click **Advanced → Go to [app name] (unsafe)**. This is normal for personal-use apps.

### Running the Fetch

```bash
# Fetch data + run analysis in one command
uv run python scripts/run_full_pipeline.py

# Or separately:
uv run python scripts/fetch_youtube_data.py      # Pulls data to data/api_fetch_<timestamp>/
uv run python scripts/youtube_analytics.py         # Analyzes the latest fetch

# Analyze a specific fetch directory
uv run python scripts/youtube_analytics.py --data-dir data/api_fetch_2026-04-30_120000

# Or analyze manual exports (fallback)
uv run python scripts/youtube_analytics.py --data-dir "Content 2024-07-14_2026-04-30 Jorge Venegas Photo"
```

### What Gets Fetched

| File | Contents |
|------|----------|
| `Table data.csv` | Per-video lifetime summary (views, watch time, likes, comments, shares, subscribers, retention) |
| `Chart data.csv` | Daily views and watch time per video |
| `Totals.csv` | Channel-level daily totals |

**API Limitations:**
- Impressions and CTR may not be available for all channels via the API v2
- If missing, CTR will show 0.00% in the analysis — all other metrics work fine
- Revenue data requires the separate YouTube Reporting API (not included here)

---

## Manual YouTube Studio Export (Fallback)

If the API isn't set up, export from YouTube Studio → Analytics → Advanced Mode.

### Export Process

1. Open YouTube Studio → Analytics → Advanced Mode
2. Select date range (recommend: last 90 days minimum, 1 year preferred)
3. For each report type, click the dropdown in the top-right → Export → Current view as CSV
4. Repeat for: Overview, Reach, Engagement, Audience, Revenue (if applicable)

### Typical File Names

YouTube exports often follow these patterns:
- `Chart data.csv` — Overview metrics over time
- `Table data.csv` — Video-level aggregate metrics
- `Traffic source - ...csv` — Traffic breakdowns
- `Viewer age.csv`, `Viewer gender.csv` — Demographics
- `Subscription status.csv`, `Subscription source.csv` — Subscriber data
- `New and returning viewers.csv` — Audience loyalty

---

## Loading & Inspection

Use pandas. Always inspect before cleaning. Run via uv:

```bash
uv run python -c "
import pandas as pd
df = pd.read_csv('Table data.csv', skiprows=1)
print(df.head())
print(df.info())
print(df.describe())
"
```

**Common issues to check:**
- Header row offset (YouTube sometimes adds a title row)
- Column names with spaces or special characters
- Percentage strings (e.g., `"4.5%"`) instead of floats
- Duration strings (e.g., `"4:32"`) instead of seconds
- Date formats varying by locale

---

## Cleaning Recipes

### Fix percentage columns

```python
df["CTR"] = df["CTR"].str.rstrip("%").astype(float) / 100
```

Or run inline with uv:

```bash
uv run python -c "
import pandas as pd
df = pd.read_csv('Table data.csv', skiprows=1)
df['CTR'] = df['CTR'].str.rstrip('%').astype(float) / 100
print(df[['Video', 'CTR']].head())
"
```

### Convert duration strings to seconds

```python
def duration_to_seconds(d):
    parts = str(d).split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return pd.NA

df["Duration (seconds)"] = df["Video duration"].apply(duration_to_seconds)
```

### Parse dates

```python
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
```

### Normalize video titles

```python
df["Video clean"] = df["Video"].str.strip().str.lower()
```

---

## Merging Multiple Files

Use video title or a synthetic key. If titles match exactly:

```python
merged = video_df.merge(
    engagement_df,
    on="Video",
    how="outer",
    suffixes=("", "_eng")
)
```

If titles differ slightly across exports, fuzzy match:

```python
from difflib import get_close_matches

def fuzzy_merge(left, right, on, threshold=0.85):
    right_map = {k: k for k in right[on]}
    left[on + "_matched"] = left[on].apply(
        lambda x: get_close_matches(x, right_map.keys(), n=1, cutoff=threshold)[0]
        if get_close_matches(x, right_map.keys(), n=1, cutoff=threshold) else x
    )
    return left.merge(right, left_on=on + "_matched", right_on=on, how="left")
```

---

## Handling Partial Data

If the user only has one file (e.g., just `Table data.csv`):
- Calculate what you can with available columns
- Skip ratios requiring missing data
- Still segment by title patterns and duration

---

## Running Scripts

The bundled helper scripts use uv:

```bash
# Full pipeline: fetch + analyze
uv run python scripts/run_full_pipeline.py

# Analysis only (auto-detects latest data)
uv run python scripts/youtube_analytics.py

# Analysis with specific directory
uv run python scripts/youtube_analytics.py --data-dir "path/to/export"
```

---

## Quick Validation Checklist

- [ ] uv venv created and dependencies installed (`uv venv && uv pip install pandas numpy google-api-python-client google-auth-httplib2 google-auth-oauthlib`)
- [ ] If using API: `scripts/client_secret.json` exists and OAuth consent screen is set to External
- [ ] If using API: your email is added as a Test user
- [ ] Row count makes sense (matches expected video count)
- [ ] No duplicate video titles after cleaning
- [ ] Date range matches what user requested
- [ ] Percentage columns are 0-1 floats, not strings
- [ ] No negative values in views, likes, watch time
- [ ] Missing data handled explicitly (not silently ignored)
