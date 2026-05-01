---
name: analyzing-youtube-analytics
description: Analyze YouTube Studio analytics data to identify high-performing content patterns, conversion drivers, and content strategy insights. Use when the user wants to understand video performance, audience engagement, what content works or doesn't, or when working with YouTube CSV exports, view counts, likes, comments, CTR, retention, or subscriber conversion data.
---

# Analyzing YouTube Analytics

Guide for analyzing YouTube Studio data to determine what content drives engagement and conversion.

## When to Use

- User provides YouTube analytics CSV exports
- User wants to understand why some videos perform better
- User asks about content strategy, audience retention, or conversion
- Comparing video performance across topics, formats, or time periods
- Setting up automated analytics fetching

## Data Sources

### Option A: Automated API Fetch (Recommended)

The skill includes a script that pulls data directly from the **YouTube Analytics API** — no manual CSV exports needed.

**One-time setup:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **YouTube Analytics API** and **YouTube Data API v3**
3. **APIs & Services → OAuth consent screen** → Set **User Type** to **External**
4. Add your email under **Test users**
5. **Credentials → Create OAuth 2.0 Client ID** (Desktop app)
6. Download the JSON → save as `scripts/client_secret.json`
7. Install dependencies: `uv pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`
8. Run once to authenticate: `uv run python scripts/fetch_youtube_data.py` (browser opens)

**After setup, run anytime:**
```bash
# Fetch fresh data + analyze + serve web report
uv run python scripts/run_full_pipeline.py

# Or separately:
uv run python scripts/fetch_youtube_data.py      # Pull data
uv run python scripts/youtube_analytics.py         # Run text analysis
uv run python scripts/serve_report.py              # Generate interactive dashboard
```

**What's fetched:**
- Per-video lifetime metrics (views, watch time, retention, likes, comments, shares, subscribers)
- Daily video breakdowns
- Channel-level daily totals
- Per-video traffic sources (how viewers discover each video: search, suggested, browse, external, etc.)
- Search terms (actual YouTube search queries driving traffic to each video)
- Geography (views, watch time, subscribers by country per video)
- Device type (mobile, desktop, TV, tablet breakdown per video)
- Content type (short vs videoOnDemand vs liveStream per video)
- Demographics (age group and gender breakdown per video)
- Retention curves (audience watch ratio at each point in the video)

**Note:** Impressions/CTR may be unavailable via API for some channels. If so, CTR will show 0.00% — the rest of the analysis still works.

### Option B: Manual YouTube Studio Exports (Fallback)

If the API isn't set up, ask the user to export from YouTube Studio (Advanced Mode → Export):

| Report | File Pattern | Key Columns |
|--------|-------------|-------------|
| Video analytics | `Video` | Video, Views, Watch time, Avg view duration, Impressions, CTR |
| Audience retention | `Retention` | Video, Retention percentage at intervals |
| Traffic source | `Traffic source` | Video, Source, Views, Watch time |
| Demographics | `Viewer age/gender` | Age/gender, Views, Avg view duration |
| Engagement | `Engagement` or per-video | Likes, Comments, Shares, Subscribers gained |
| Revenue (if monetized) | `Revenue` | Video, Estimated revenue, RPM |

If the user only has partial data, work with what's available.

## Environment Setup

This skill uses **uv** for Python environment management. If not already set up:

```bash
uv venv .venv
uv pip install pandas numpy

# For API fetching (recommended)
uv pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

Run scripts with: `uv run python scripts/<script>.py ...`

## Web Report

Generate and serve an interactive HTML dashboard with charts, tables, and funnel diagnosis.

```bash
# Generate report + auto-open in browser
uv run python scripts/serve_report.py

# Custom port
uv run python scripts/serve_report.py --port 8080

# Just generate report.html (no server)
uv run python scripts/serve_report.py --no-serve

# Analyze specific data directory
uv run python scripts/serve_report.py --data-dir data/api_fetch_2026-04-30_120000
```

The dashboard includes:
- **KPI cards** with channel snapshot metrics
- **Interactive charts** (Chart.js): views by topic/format, top videos, correlations, weekly trends
- **Sortable tables** for top/bottom performers, segment analysis, funnel diagnosis
- **Top 20% vs Bottom 20%** comparison panel
- **Deep dives**: highest engagement, best subscriber conversion, top momentum

## Async Researcher Agent (LLM-Powered)

For **deep, LLM-powered analysis** that runs concurrently with the web report, the pi harness dispatches a `youtube-researcher` sub-agent. The agent reads the raw CSVs, uses its reasoning capabilities to identify patterns, diagnose problems, and write a comprehensive markdown report.

### Two-Step Workflow

**Step 1:** Fetch data and start the web server
```bash
uv run python scripts/run_full_pipeline.py
```
This fetches data and starts the server. The web report shows raw metrics immediately.

**Step 2:** Dispatch the researcher agent (in pi)
```
Dispatch the youtube-researcher agent on data/latest
```
Or with a specific directory:
```
Dispatch the youtube-researcher agent on data/api_fetch_2026-04-30_120000
```

The agent will:
1. Read all CSV files (Table data.csv, Traffic sources.csv, Search terms.csv, etc.)
2. Run `scripts/researcher.py` for baseline statistics
3. Apply LLM reasoning to identify patterns, diagnose problems, find gaps
4. Write `reports/research_<timestamp>.md` with actionable insights

### What the Researcher Analyzes

- **What works:** Content types, durations, traffic sources, and demographics of top performers
- **What doesn't work:** Diagnostic flags (discovery problem vs retention problem) for underperformers
- **Content gaps:** High-performing topics with few videos, underserved search terms
- **New content ideas:** 5-10 specific, actionable video ideas based on data patterns
- **Action plan:** Prioritized quick wins, medium-term bets, and long-term experiments

### Output

- `reports/research_<timestamp>.md` — Written analysis with LLM insights
- `reports/enriched_<timestamp>.csv` — Per-video recommendations and anomaly flags

The web report footer automatically shows research status and links to the report when complete.

### Parallel Sub-Agents (Optional)

For channels with 50+ videos, the researcher can fan out into parallel sub-tasks:
- **Content Type Analyst** — which formats drive engagement
- **Traffic Source Analyst** — where discovery succeeds vs fails
- **Search Term Analyst** — keyword gaps and opportunities
- **Retention Analyst** — hook quality, drop-off points
- **Idea Generator** — synthesizes findings into actionable content ideas

## Core Workflow

Copy this checklist and track progress:

```
- [ ] 0. Set up uv venv (uv venv + uv pip install pandas numpy google-api-python-client ...)
- [ ] 1. Fetch data (API auto-fetch OR load manual CSVs)
- [ ] 2. Load and inspect all data
- [ ] 3. Clean data (parse dates, normalize video titles/IDs)
- [ ] 4. Calculate derived metrics and ratios
- [ ] 5. Segment and compare content groupings
- [ ] 6. Identify patterns in top/bottom performers
- [ ] 7. Produce findings and actionable recommendations
- [ ] 8. Generate interactive web report (serve_report.py)
```

### Step 1: Load & Inspect

**If using API:** Data is auto-saved to `data/api_fetch_<timestamp>/` with these files:
- `Table data.csv` — per-video lifetime summary
- `Chart data.csv` — daily breakdown per video
- `Totals.csv` — channel-level daily totals
- `Traffic sources.csv` — per-video traffic source breakdown (search, suggested, browse, etc.)
- `Search terms.csv` — top YouTube search queries driving traffic to each video
- `Geography.csv` — per-video country breakdown (views, watch time, subscribers)
- `Device type.csv` — per-video device breakdown (mobile, desktop, TV, etc.)
- `Content type.csv` — per-video content type (short, videoOnDemand, liveStream)
- `Demographics.csv` — per-video age/gender viewer percentage breakdown
- `Retention.csv` — per-video audience retention curves (watch ratio + relative retention at each time point)

**If using manual exports:** Load all CSVs. Note column names and date ranges. Identify the primary key for joining (usually video title or ID). Flag missing data.

### Step 2: Clean & Merge

- Parse `Date` columns to datetime
- Normalize video titles (strip whitespace, handle duplicates)
- Join related tables on video identifier
- Handle missing values (0 for missing engagement, drop if core metrics missing)

### Step 3: Calculate Derived Metrics

Compute these ratios per video:

| Metric | Formula | What It Reveals |
|--------|---------|-----------------|
| Engagement rate | `(likes + comments) / views` | Content resonance |
| Like rate | `likes / views` | Approval intensity |
| Comment rate | `comments / views` | Discussion driver |
| CTR | `clicks / impressions` | Thumbnail/title appeal |
| AVD / duration | `avg view duration / video length` | Retention efficiency |
| Conversion rate | `subscribers gained / views` | Subscriber magnetism |
| Watch time per view | `watch time / views` | Depth of engagement |

### Step 4: Segment & Compare

Group videos by attributes the user can control:

- **Topic/theme** — parse from titles or tags
- **Format** — short, tutorial, review, vlog, etc.
- **Duration bucket** — <1min, 1-5min, 5-10min, 10min+
- **Publish day/hour** — day of week, time of day
- **Thumbnail style** — text-heavy, face, product, etc. (if metadata available)

For each segment, compare:
- Mean/median views, engagement rate, CTR, AVD ratio
- Variance (consistency vs. hit-driven)
- Top and bottom 20% performers

### Step 5: Identify Patterns

**Top performer analysis:**
- What do top 20% videos have in common?
- Are high views driven by CTR, retention, or both?
- Do high-engagement videos also convert subscribers?

**Underperformer analysis:**
- Do low-view videos have low CTR (discovery problem) or low retention (content problem)?
- Is there a duration or format pattern in underperformers?

**Correlation checks:**
- Views vs. engagement rate (quality vs. quantity)
- CTR vs. AVD ratio (clickbait detection)
- Watch time per view vs. subscribers gained

### Step 6: Report Findings

Structure output using the template in [references/report-template.md](references/report-template.md).

Prioritize actionable recommendations the user can implement in their next 3-5 videos.

## Key Principles

1. **Distinguish discovery from retention problems**: Low CTR = fix thumbnail/title. Low AVD = fix pacing/hook/content.
2. **Look for segment winners, not just individual hits**: One viral video is luck; a pattern across a segment is strategy.
3. **Engagement rate > raw views**: A video with fewer views but higher engagement rate often indicates a stronger niche.
4. **Control for time**: Newer videos have less data. Normalize by days since publish if comparing across dates.

## References

- **Data preparation**: [references/data-preparation.md](references/data-preparation.md) — loading, cleaning, joining CSVs; API setup
- **Analysis framework**: [references/analysis-framework.md](references/analysis-framework.md) — deep dives into metrics, segmentation, and pattern detection
- **Report template**: [references/report-template.md](references/report-template.md) — structured output format
