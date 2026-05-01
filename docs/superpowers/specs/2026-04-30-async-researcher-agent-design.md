# Async Researcher Agent Design

> For: `analyzing-youtube-analytics` skill
> Date: 2026-04-30

## Goal

Add a background researcher agent that runs concurrently with the web report server. The user gets instant access to raw data via the existing web report, while deep analysis (what works, what doesn't, new content ideas) runs asynchronously and writes its results to disk.

## Architecture

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Fetch API  │────▶│  Start Server   │────▶│ Launch Research │
│    Data     │     │  (background)   │     │  (async agent)  │
└─────────────┘     └─────────────────┘     └─────────────────┘
                            │                        │
                            ▼                        ▼
                     User browses raw           Writes reports/
                     data immediately           enriched CSVs
```

## Components

### 1. Pipeline Orchestrator (`scripts/run_full_pipeline.py`)

After fetch, the pipeline:
1. Starts the web server as a **background subprocess** (`subprocess.Popen`)
2. Launches the researcher as an **async sub-agent** via `pi-subagents`
3. Prints both URLs/status to the user
4. Waits for Ctrl+C, then cleans up the server (researcher continues independently)

New CLI flags:
- `--no-research` — skip researcher, just fetch + serve (existing behavior with server)
- `--research-only` — skip server, just fetch + research

### 2. Web Server (`scripts/serve_report.py`)

Add a **Research Status** badge in the page footer:
- While research is running: "Research in progress..." (spinner/loading state)
- When research completes: clickable link to `reports/research_<timestamp>.md`
- If no research was launched: hidden or shows "No research queued"

The status is updated via a simple JSON poll or file-watcher pattern. Since the server is already Python, the simplest approach is to check for the existence of the research report file on each page load and render the appropriate footer state.

### 3. Researcher Core (`scripts/researcher.py`)

A standalone Python script that:
1. Loads all CSVs from a given data directory
2. Runs deep analysis
3. Writes two outputs:
   - `reports/research_<timestamp>.md` — human-readable research report
   - `reports/enriched_<timestamp>.csv` — per-video enriched data

**Input:** data directory path (e.g., `data/api_fetch_2026-04-30_210136`)
**Output:** `reports/research_<timestamp>.md` + `reports/enriched_<timestamp>.csv`

### 4. Researcher Agent Definition

Defined as a pi sub-agent (via `subagent create` or inline config) with:
- **System prompt:** Expert YouTube analytics researcher. Analyzes data to identify patterns, diagnose problems, and generate actionable content ideas.
- **Tools:** `read`, `bash`, `edit`, `write` — to read CSVs, run analysis code, write reports
- **Task:** Run `scripts/researcher.py` with the data directory, then review and improve the generated report

### 5. Researcher Sub-Agents (Parallel Fan-Out)

The researcher can optionally fan out into parallel sub-tasks:
- **Content Type Analyst** — which formats/types drive engagement
- **Traffic Source Analyst** — where discovery succeeds vs fails
- **Search Term Analyst** — keyword gaps and opportunities
- **Retention Analyst** — hook quality, drop-off points, relative retention patterns
- **Idea Generator** — synthesizes findings into actionable content ideas

Each sub-agent gets the same data directory, focuses on one domain, and writes its findings to a temporary file. The parent researcher merges these into the final report.

**Parallelization is triggered by:** a `--deep-research` flag on the researcher, or automatically when the dataset exceeds a threshold (e.g., >50 videos).

## Deep Research Output

### Report (`reports/research_<timestamp>.md`)

Sections:
1. **Executive Summary** — top 3 findings, top 3 recommendations
2. **What Works** — patterns in top 20% performers by content type, duration, traffic source, demographics
3. **What Doesn't Work** — patterns in bottom 20%, with diagnostic flags (discovery problem vs retention problem)
4. **Content Gaps** — high-performing topics/formats with few videos, underserved search terms
5. **Retention Insights** — videos with strong hooks but weak retention (fix pacing), weak hooks but strong retention (fix thumbnails)
6. **New Content Ideas** — 5-10 specific, actionable video ideas based on data patterns
7. **Action Plan** — prioritized list of what to do next (quick wins vs longer-term bets)

### Enriched Data (`reports/enriched_<timestamp>.csv`)

Columns added to the per-video summary:
- `anomaly_flag` — unexpected spike or drop (z-score based)
- `trend_direction` — accelerating / flat / declining (based on daily views slope)
- `recommendation` — one of: `double_down`, `fix_thumbnail`, `improve_hook`, `expand_series`, `deprecate`
- `content_opportunity_score` — 0-100 score based on gap analysis
- `search_gap_keywords` — comma-separated list of high-volume, low-competition search terms this video could target

## File Changes

| File | Action |
|------|--------|
| `scripts/run_full_pipeline.py` | Add server background start + async researcher launch; add `--no-research` flag |
| `scripts/serve_report.py` | Add Research Status badge in footer |
| `scripts/researcher.py` | New — core research logic |
| `.pi/skills/analyzing-youtube-analytics/SKILL.md` | Document researcher feature and new CLI flags |
| `.pi/skills/analyzing-youtube-analytics/scripts/run_full_pipeline.py` | Sync changes |
| `.pi/skills/analyzing-youtube-analytics/scripts/serve_report.py` | Sync changes |
| New: `agents/youtube-researcher` (or inline config) | Sub-agent definition |
| New: `reports/` | Output directory (gitignored) |

## Error Handling

- **Server fails to start:** Print error, still launch researcher (user gets report later)
- **Researcher fails:** Print error to console, server continues running with raw data
- **Researcher times out:** Set a 5-minute timeout; if exceeded, kill and log partial results
- **Missing data files:** Skip analysis sections that depend on missing CSVs; still produce partial report

## Testing Plan

- Unit test `researcher.py` with a small fixture dataset (5-10 videos)
- Verify report markdown is well-formed
- Verify enriched CSV has all expected columns
- Test pipeline with `--no-research` flag
- Test that server starts before researcher finishes
- Test sub-agent parallel fan-out with mock data

## Dependencies

No new Python dependencies. Uses existing: `pandas`, `numpy`, `scipy` (for z-scores), `sklearn` (optional, for clustering).

The `pi-subagents` skill is used for async agent launching — this is a harness feature, not a Python dependency.
