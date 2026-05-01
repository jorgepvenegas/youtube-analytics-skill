# YouTube Analytics API Expansion Plan

Proposed additions to `fetch_youtube_data.py` — data the skill is **not** currently extracting but is available via the YouTube Analytics API v2.

---

## Current State

The fetcher already pulls:

| Dataset | Dimensions | Metrics |
|---------|-----------|---------|
| Per-video lifetime summary | `video` | `views`, `estimatedMinutesWatched`, `averageViewDuration`, `averageViewPercentage`, `subscribersGained`, `subscribersLost`, `likes`, `comments`, `shares` |
| Daily video breakdown | `day`, `video` | `views`, `estimatedMinutesWatched` |
| Channel daily totals | `day` | `views`, `estimatedMinutesWatched`, `subscribersGained`, `subscribersLost` |
| Video metadata | — | `title`, `publishedAt`, `duration` (from YouTube Data API v3) |

**Known gaps:**
- `Impressions` and `CTR` are **not** fetched (API returns 0 for some channels; Studio export is the only reliable source)
- No traffic source, geography, demographics, device, retention curve, or search term data

---

## Proposed Additions

### 1. Traffic Sources (`insightTrafficSourceType`)

**Why it matters:** Reveals *how* viewers discover each video. A video with high views from "YouTube Search" needs strong SEO/title optimization. One from "Suggested Videos" needs clickable thumbnails. One from "Browse" indicates strong subscriber loyalty. Without this, you can't diagnose discovery problems accurately.

**API call:**
```python
fetch_report(
    analytics,
    dimensions=["video", "insightTrafficSourceType"],
    metrics=["views", "estimatedMinutesWatched"],
    filters=f"video=={vid_filter}",
)
```

**Output file:** `Traffic sources.csv`

**Schema:**
| Column | Type | Notes |
|--------|------|-------|
| Video | str | Video ID |
| Video title | str | Joined from metadata |
| Traffic source | str | `YT_SEARCH`, `SUGGESTED`, `BROWSE`, `EXT_URL`, `NOTIFICATION`, `CHANNEL`, `PLAYLIST`, `END_SCREEN`, `ANNOTATION`, `SUBSCRIBERS`, `HASHTAGS`, `SHORTS`, etc. |
| Views | int | |
| Watch time (hours) | float | `estimatedMinutesWatched / 60` |

**Analysis opportunity:**
- Per-video traffic mix pie chart
- Segment by source: "Videos with >50% search views average X CTR"
- Identify underutilized sources (e.g., no traffic from playlists = playlist optimization opportunity)

---

### 2. Search Terms (`insightTrafficSourceDetail` + `YT_SEARCH` filter)

**Why it matters:** The actual queries people type into YouTube to find your videos. Directly actionable for SEO, title optimization, and content gap analysis. If "canon eos r5 setup guide" drives 500 views but you don't have a video with that exact title, that's a content opportunity.

**API call:**
```python
fetch_report(
    analytics,
    dimensions=["video", "insightTrafficSourceDetail"],
    metrics=["views", "estimatedMinutesWatched"],
    filters=f"video=={vid_filter};insightTrafficSourceType==YT_SEARCH",
    sort="-views",
    max_results=25,
)
```

**Output file:** `Search terms.csv`

**Schema:**
| Column | Type | Notes |
|--------|------|-------|
| Video | str | Video ID |
| Video title | str | Joined from metadata |
| Search term | str | Raw query string |
| Views | int | |
| Watch time (hours) | float | |

**Analysis opportunity:**
- Top search terms across all videos (word cloud / frequency table)
- Search term → video mapping: which terms drive traffic to which videos?
- Content gap: high-volume search terms with no dedicated video
- Title optimization: are your titles matching the actual search queries?

**Limitation:** Data is thresholded. Very low-volume terms are hidden by YouTube.

---

### 3. Audience Retention Curves (`elapsedVideoTimeRatio`)

**Why it matters:** The current fetcher only provides `averageViewPercentage` — a single scalar. Retention curves show *where* viewers drop off. Two videos with 50% AVD can have completely different curves: one drops off immediately (bad hook), one holds steady then drops at the end (good content, natural decay). Critical for comparing intros, pacing, and identifying structural problems.

**API call:**
```python
# ONE video at a time — API restriction
fetch_report(
    analytics,
    dimensions=["elapsedVideoTimeRatio"],
    metrics=["audienceWatchRatio", "relativeRetentionPerformance"],
    filters=f"video=={video_id};audienceType==ORGANIC",
)
```

**Output file:** `Retention/{video_id}.csv` (one file per video, or single merged file)

**Schema:**
| Column | Type | Notes |
|--------|------|-------|
| Video | str | Video ID |
| Video title | str | Joined from metadata |
| Elapsed ratio | float | 0.0 to 1.0 (0% to 100% of video length) |
| Audience watch ratio | float | % of viewers still watching at this point |
| Relative retention | float | vs. similar-length videos (1.0 = average, >1 = above average) |

**Analysis opportunity:**
- Compare retention curves across topic/format
- Identify "cliff" points — where do most viewers leave?
- Hook analysis: first 15 seconds retention by format
- Relative retention flag: videos consistently below 1.0 need structural work regardless of topic

**Implementation note:** Must loop through videos individually. For 100 videos = 100 API calls. Consider caching and only fetching for top/bottom performers or new uploads.

---

### 4. Geography (`country`)

**Why it matters:** Viewing behavior varies by region. If 40% of your audience is from non-English-speaking countries, that might explain lower engagement rates on text-heavy thumbnails. If a specific country over-indexes for subscriber conversion, consider content tailored to that market. Also useful for upload time optimization.

**API call:**
```python
fetch_report(
    analytics,
    dimensions=["video", "country"],
    metrics=["views", "estimatedMinutesWatched", "subscribersGained"],
    filters=f"video=={vid_filter}",
)
```

**Output file:** `Geography.csv`

**Schema:**
| Column | Type | Notes |
|--------|------|-------|
| Video | str | Video ID |
| Video title | str | Joined from metadata |
| Country | str | ISO country code |
| Views | int | |
| Watch time (hours) | float | |
| Subscribers gained | int | |

**Analysis opportunity:**
- Top countries by views / watch time / subscriber conversion
- Per-video geographic concentration (diversity index)
- "Global appeal" score: does a video perform well across regions or is it niche?
- Optimal upload time based on top-country timezone

---

### 5. Device Type (`deviceType`)

**Why it matters:** Mobile viewers scroll quickly and have shorter attention spans. TV viewers are more captive but can't click links easily. Tablet viewers behave differently too. If your tutorials are watched 70% on TV, you might want longer, more in-depth content. If your POV videos are 90% mobile, vertical-friendly thumbnails and fast cuts matter more.

**API call:**
```python
fetch_report(
    analytics,
    dimensions=["video", "deviceType"],
    metrics=["views", "estimatedMinutesWatched"],
    filters=f"video=={vid_filter}",
)
```

**Output file:** `Device type.csv`

**Schema:**
| Column | Type | Notes |
|--------|------|-------|
| Video | str | Video ID |
| Video title | str | Joined from metadata |
| Device | str | `MOBILE`, `DESKTOP`, `TABLET`, `TV`, `GAME_CONSOLE` |
| Views | int | |
| Watch time (hours) | float | |

**Analysis opportunity:**
- Device mix by format (Shorts vs tutorials vs reviews)
- AVD correlation with TV % (TV viewers watch longer?)
- Thumbnail readability: mobile-first vs desktop-first design

---

### 6. Content Type (`creatorContentType`)

**Why it matters:** YouTube segments performance by Shorts, Video On Demand (regular), and Live. Your current analysis mixes them all together. A Short with 2K views and a 10-minute tutorial with 2K views are not comparable. Separating them is essential for fair benchmarking.

**API call:**
```python
fetch_report(
    analytics,
    dimensions=["video", "creatorContentType"],
    metrics=["views", "estimatedMinutesWatched", "averageViewPercentage", "subscribersGained"],
    filters=f"video=={vid_filter}",
)
```

**Output file:** `Content type.csv` (or add as a column to existing `Table data.csv`)

**Schema:**
| Column | Type | Notes |
|--------|------|-------|
| Video | str | Video ID |
| Video title | str | |
| Content type | str | `short`, `videoOnDemand`, `liveStream` |
| Views | int | |
| Watch time (hours) | float | |
| Avg % viewed | float | |
| Subscribers gained | int | |

**Analysis opportunity:**
- Separate dashboards/tables per content type
- Compare Shorts vs long-form engagement patterns
- Content type strategy: where to invest effort?

---

### 7. Demographics (`ageGroup`, `gender`)

**Why it matters:** Confirms audience assumptions. If you think you're making content for 25-34 year old men but the data shows 45-54 women, that's a massive strategic insight. Also critical for sponsorship pitches.

**API call:**
```python
fetch_report(
    analytics,
    dimensions=["video", "ageGroup", "gender"],
    metrics=["viewerPercentage"],
    filters=f"video=={vid_filter}",
)
```

**Output file:** `Demographics.csv`

**Schema:**
| Column | Type | Notes |
|--------|------|-------|
| Video | str | Video ID |
| Video title | str | |
| Age group | str | `13-17`, `18-24`, `25-34`, `35-44`, `45-54`, `55-64`, `65+` |
| Gender | str | `male`, `female`, `user_specified` |
| Viewer % | float | % of logged-in viewers in this demographic |

**Analysis opportunity:**
- Channel-wide demographic profile
- Per-topic demographic skew (e.g., "Film/Olympus skews older than Canon EOS R")
- Engagement correlation: do certain demographics engage more?

**Limitation:** Only logged-in viewers. Anonymous viewers are excluded, so totals won't match view counts exactly.

---

## Phased Implementation Plan

### Phase 1: Quick Wins (same API call pattern as existing)
- [x] Traffic sources
- [x] Geography
- [x] Device type
- [x] Content type

These all use the same `fetch_report` pattern with `video` filter — can batch in one loop, similar to existing daily breakdown.

### Phase 2: Search & Demographics (slightly different patterns)
- [x] Search terms (requires `insightTrafficSourceType==YT_SEARCH` filter + `maxResults`)
- [x] Demographics (only `viewerPercentage` metric, no views/watch time)

### Phase 3: Retention Curves (most complex)
- [x] Retention curves (one API call per video — needs rate-limiting and caching)
- [x] Consider fetching only for: top 20 videos, bottom 20 videos, and any video uploaded in last 30 days

---

## File Structure After Expansion

```
data/api_fetch_2026-04-30_120000/
├── Table data.csv              # existing
├── Chart data.csv              # existing
├── Totals.csv                  # existing
├── Traffic sources.csv         # NEW
├── Search terms.csv            # NEW
├── Geography.csv               # NEW
├── Device type.csv             # NEW
├── Content type.csv            # NEW
├── Demographics.csv            # NEW
└── Retention/                  # NEW directory
    ├── abc123.csv
    ├── def456.csv
    └── ...
```

---

## Dashboard Integration Ideas

| New Dataset | Dashboard Section |
|-------------|-------------------|
| Traffic sources | Per-video pie charts; segment performance by source |
| Search terms | Word cloud; "content gaps" table; top terms by topic |
| Retention curves | Per-video retention graph; average curve by format; cliff detection |
| Geography | World map (or bar chart) of views; top countries table; per-video heatmap |
| Device type | Device mix donut chart; AVD by device; format × device matrix |
| Content type | Filter/switcher on all charts; separate KPI cards per type |
| Demographics | Age/gender bar charts; topic × demographic heatmap |

---

## Open Questions

1. **Retention API rate limits:** 1 call per video. With 100 videos, that's 100 quota units + latency. Should we:
   - Fetch all videos (slow but complete)?
   - Fetch only top 30 + bottom 20 + recent uploads?
   - Cache retention data and only fetch new videos?

2. **Search term thresholds:** YouTube hides low-volume terms. Should we merge historical search term data across multiple fetches to build a larger corpus?

3. **Impressions/CTR:** The API often returns 0 for these. Should we add a fallback that prompts the user to upload a Studio CSV export for just the impressions/CTR columns, then merge into the API-fetched data?

4. **Scope expansion:** Demographics and some retention metrics may require the broader `youtube.readonly` scope (already in our SCOPES list). Monetization data would require `yt-analytics-monetary.readonly` — out of scope unless user is in YPP and explicitly asks.

---

*Last updated: 2026-04-30*
