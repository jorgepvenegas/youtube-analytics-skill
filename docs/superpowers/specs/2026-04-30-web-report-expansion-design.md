# Web Report Expansion Design

**Goal:** Add 7 new data sections to the web report using the new CSV files from the expanded pipeline, replace hardcoded topic/format classification with data-driven content type segmentation, and clean up stale photography-specific code.

**File:** `scripts/serve_report.py` (single file, ~948 lines currently)

---

## Data Sources

The pipeline now produces these CSVs in `data/api_fetch_<timestamp>/`:

| File | Columns | Used in section |
|------|---------|----------------|
| `Table data.csv` | Video metrics (existing) | Channel Snapshot, Top/Bottom, Funnel, Deep Dives |
| `Chart data.csv` | Daily breakdown (existing) | — |
| `Totals.csv` | Channel daily totals (existing) | Weekly Trend |
| `Traffic sources.csv` | Video, Video title, Traffic source, Views, Watch time (hours) | Traffic Sources |
| `Search terms.csv` | Video, Video title, Search term, Views, Watch time (hours) | Search Terms |
| `Geography.csv` | Video, Video title, Country, Views, Watch time (hours), Subscribers gained | Geography |
| `Device type.csv` | Video, Video title, Device, Views, Watch time (hours) | Device Breakdown |
| `Content type.csv` | Video, Video title, Content type, Views, Watch time (hours), Avg % viewed, Subscribers gained | Content Type Breakdown |
| `Demographics.csv` | Video, Video title, Age group, Gender, Viewer % | Demographics |
| `Retention.csv` | Video, Video title, Elapsed ratio, Audience watch ratio, Relative retention | Retention Curves |

All new CSVs are optional — if a file doesn't exist, the corresponding section is silently skipped. This keeps the report working for older data directories or channels where some API calls return empty data.

---

## Sections (in order)

### 1. Channel Snapshot (existing, no changes)
KPI cards: views, watch time, subs, engagement, etc.

### 2. Content Type Breakdown (NEW — replaces Topic + Format segments)
- **Data:** `Content type.csv`
- **Chart:** Bar chart — views by content type (`short`, `videoOnDemand`, `liveStream`)
- **Table:** One row per content type with columns: Videos (count), Views, Watch time (hours), Avg % viewed, Subscribers gained
- Aggregated from per-video rows by grouping on `Content type`

### 3. Traffic Sources (NEW)
- **Data:** `Traffic sources.csv`
- **Chart:** Doughnut chart — channel-wide traffic source mix (aggregate all videos by source, show % of total views)
- **Table:** Ranked by views — columns: Traffic source, Views, Watch time (hours), % of total views
- Aggregate by summing views/watch time per `Traffic source` across all videos

### 4. Search Terms (NEW)
- **Data:** `Search terms.csv`
- **Table:** All rows sorted by views descending — columns: #, Search term, Video title, Views, Watch time (hours)
- No chart needed — table is the right format for text data

### 5. Geography (NEW)
- **Data:** `Geography.csv`
- **Chart:** Horizontal bar chart — top 10 countries by views
- Aggregate by summing views/watch time/subs per `Country` across all videos
- Sort by views descending, take top 10

### 6. Device Breakdown (NEW)
- **Data:** `Device type.csv`
- **Chart:** Doughnut chart — channel-wide device mix (% of views by device)
- Aggregate by summing views per `Device` across all videos

### 7. Demographics (NEW)
- **Data:** `Demographics.csv`
- **Chart:** Stacked bar chart — age groups on X axis, bars split by gender
- Aggregate across all videos: for each age group + gender combo, average the `Viewer %`
- Only show demographics data if the CSV has rows (some channels have very limited demographic data)

### 8. Retention Curves (NEW)
- **Data:** `Retention.csv`
- **Interactive:** Dropdown `<select>` listing all videos that have retention data
- **Chart:** Line chart with two datasets:
  - Solid line: `Audience watch ratio` (Y) vs `Elapsed ratio` (X, 0-100%)
  - Dashed line: `Relative retention` (vs similar-length videos, 1.0 = average)
- On dropdown change, update the chart with the selected video's data
- Default: first video in the list

### 9. Performance Charts (existing, modified)
- Remove topic chart and format chart (replaced by content type in section 2)
- Keep: Top 15 videos bar chart, correlation chart, weekly trend chart

### 10. Top/Bottom Videos (existing, modified)
- Remove `Topic` and `Format` columns from the table
- Add `Content type` column (joined from `Content type.csv` by video ID)
- Add `Top source` column (the traffic source with most views for that video, from `Traffic sources.csv`)

### 11. Segment Analysis: By Duration (existing, no changes)
Duration bucket table — already data-driven.

### 12. Top 20% vs Bottom 20% (existing, modified)
- Remove `top_topics` and `bottom_topics` fields (hardcoded topic references)
- Keep all other comparison metrics

### 13. Funnel Diagnosis (existing, modified)
- Remove `Topic / Format` column
- Add `Content type` column
- Add `Top source` column

### 14. Deep Dives (existing, no changes)
Engagement, subscriber conversion, momentum tables.

---

## Removals

1. **`classify_title()` function** — hardcoded photography topic classifier, delete entirely
2. **`classify_format()` function** — hardcoded format classifier, delete entirely
3. **`summary['Topic']` column** — all references removed
4. **`summary['Format']` column** — all references removed
5. **Segment Analysis: By Topic table** — replaced by Content Type Breakdown
6. **Segment Analysis: By Format table** — replaced by Content Type Breakdown
7. **`topic_agg` / `fmt_agg` data structures** — no longer needed
8. **Topic/Format charts** (topicChart, formatChart) — replaced by content type chart

---

## Implementation Approach

### Data Loading
Load each new CSV with a guard:

```python
traffic_df = load_optional_csv(base / "Traffic sources.csv")
search_df = load_optional_csv(base / "Search terms.csv")
# etc.
```

Where `load_optional_csv` returns `None` if file doesn't exist. Each section checks `if df is not None` before rendering.

### Chart.js Integration
All new charts use Chart.js (already loaded via CDN). Data is passed as JSON via Python f-string interpolation into the `<script>` block, following the existing pattern.

### Retention Interactivity
The retention dropdown uses vanilla JS — no additional dependencies. On change, it filters the retention JSON array by video ID and updates the Chart.js instance via `.data.datasets[0].data = ...` + `.update()`.

### Section Order in HTML
1. Channel Snapshot
2. Content Type Breakdown
3. Traffic Sources
4. Search Terms
5. Geography + Device Breakdown (side by side in a chart-row grid)
6. Demographics
7. Retention Curves
8. Performance Charts (top videos bar, correlation, weekly trend)
9. Top 10 / Bottom 10 Videos
10. Segment Analysis: By Duration
11. Top 20% vs Bottom 20%
12. Funnel Diagnosis
13. Deep Dives

---

## Non-Goals

- No topic/format classification of any kind — content type from the API is the only segmentation besides duration buckets
- No per-video traffic source breakdown table (channel-wide aggregate is sufficient; per-video detail is in the CSV for manual analysis)
- No map visualization for geography (horizontal bar chart is simpler and more readable)
- No additional dependencies beyond Chart.js (already present)
