# pi-youtube-analytics

A [pi](https://pi.dev) skill for analyzing YouTube Studio analytics. Fetch data via the YouTube Analytics API, generate interactive HTML dashboards, and get LLM-powered deep research reports.

## Features

- **One-command data fetch** — Pulls all metrics from YouTube Analytics API (no manual CSV exports)
- **Interactive web report** — Dark-themed HTML dashboard with Chart.js charts, sortable tables, funnel diagnosis
- **7 expansion datasets** — Traffic sources, search terms, geography, device type, content type, demographics, retention curves
- **LLM-powered researcher** — Deep analysis agent that identifies patterns, diagnoses problems, and generates content ideas
- **Enriched data export** — Per-video anomaly flags, recommendations, and opportunity scores

## Installation

```bash
pi install git:github.com/yourusername/pi-youtube-analytics
```

Or for local development:

```bash
pi install ./path/to/pi-youtube-analytics
```

## One-Time Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **YouTube Analytics API** and **YouTube Data API v3**
3. **APIs & Services → OAuth consent screen** → Set **User Type** to **External**
4. Add your email under **Test users**
5. **Credentials → Create OAuth 2.0 Client ID** (Desktop app)
6. Download the JSON → save as `client_secret.json` in your project root
7. Run once to authenticate (opens browser):
   ```bash
   uv run python scripts/fetch_youtube_data.py
   ```

## Usage

### Full Pipeline (fetch + text analysis + web server)

```bash
uv run python scripts/run_full_pipeline.py
```

This fetches fresh data, runs text analysis, and starts a local web server at `http://127.0.0.1:8765`.

### Just the Web Report (on existing data)

```bash
uv run python scripts/serve_report.py --data-dir data/latest
```

### LLM-Powered Deep Research

After the server starts, dispatch the researcher agent:

```
Dispatch the youtube-researcher agent on data/latest
```

The agent reads all your CSVs, runs statistical analysis, applies LLM reasoning, and writes a comprehensive report to `reports/research_<timestamp>.md` with actionable content ideas.

### Run Researcher Standalone

```bash
uv run python scripts/researcher.py --data-dir data/latest
```

## Data Output

All fetched data is saved to `data/api_fetch_<timestamp>/`:

| File | Contents |
|------|----------|
| `Table data.csv` | Per-video lifetime summary |
| `Chart data.csv` | Daily breakdown per video |
| `Totals.csv` | Channel-level daily totals |
| `Traffic sources.csv` | Per-video traffic source breakdown |
| `Search terms.csv` | Top YouTube search queries |
| `Geography.csv` | Country-level views, watch time, subs |
| `Device type.csv` | Mobile, desktop, TV, tablet breakdown |
| `Content type.csv` | shorts vs videoOnDemand vs liveStream |
| `Demographics.csv` | Age/gender viewer percentages |
| `Retention.csv` | Audience retention curves |

## Report Output

- `report.html` — Interactive web dashboard (served locally)
- `reports/research_<timestamp>.md` — LLM-powered deep analysis
- `reports/enriched_<timestamp>.csv` — Per-video recommendations and flags

## Project Structure

```
.
├── skills/analyzing-youtube-analytics/   # Pi skill (canonical source)
│   ├── SKILL.md                          # Skill documentation
│   ├── scripts/                          # All Python scripts
│   │   ├── fetch_youtube_data.py
│   │   ├── researcher.py
│   │   ├── run_full_pipeline.py
│   │   ├── serve_report.py
│   │   └── youtube_analytics.py
│   ├── tests/                            # Test suite
│   └── references/                       # Analysis frameworks
├── agents/youtube-researcher.md          # LLM researcher agent definition
├── package.json                          # Pi package manifest
├── scripts/ → skills/.../scripts/        # Symlink for local dev
├── tests/ → skills/.../tests/            # Symlink for local dev
├── client_secret.json                    # Your OAuth credentials (gitignored)
├── token.pickle                          # Auth token (gitignored)
├── data/                                 # Fetched data (gitignored)
└── reports/                              # Generated reports (gitignored)
```

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) for Python environment management
- pandas, numpy, google-api-python-client, google-auth-oauthlib

Install dependencies:
```bash
uv pip install pandas numpy google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

## License

MIT
