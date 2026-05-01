# Traffic Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add traffic source data fetching (`insightTrafficSourceType`) to the YouTube Analytics fetcher, producing a `Traffic sources.csv` alongside existing CSVs.

**Architecture:** Add a new `fetch_traffic_sources()` function that follows the exact same pattern as `fetch_video_analytics()` — calls `fetch_report()` with the `insightTrafficSourceType` dimension, joins video titles from metadata, and saves to CSV. Wire it into `main()` as step `[5/5]`. Add tests using a fake Analytics API response to verify the data transformation logic.

**Tech Stack:** Python 3.13, pandas, google-api-python-client (already installed), pytest (add as dev dependency)

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `scripts/fetch_youtube_data.py` | Add `fetch_traffic_sources()` function + wire into `main()` |
| Create | `tests/test_fetch_traffic_sources.py` | Unit tests for traffic source data transformation |

---

### Task 1: Set Up Test Infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_fetch_traffic_sources.py`

- [ ] **Step 1: Create test directory and empty init**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 2: Install pytest**

```bash
uv pip install pytest
```

- [ ] **Step 3: Write the failing test for `fetch_traffic_sources`**

Create `tests/test_fetch_traffic_sources.py`:

```python
"""Tests for traffic source fetching and transformation."""

import pandas as pd
import pytest

# We'll import after implementation exists — for now, verify the test runs and fails
from scripts.fetch_youtube_data import fetch_traffic_sources


def make_fake_analytics():
    """Create a mock analytics service that returns canned traffic source data."""

    class FakeQuery:
        def execute(self):
            return {
                "columnHeaders": [
                    {"name": "video"},
                    {"name": "insightTrafficSourceType"},
                    {"name": "views"},
                    {"name": "estimatedMinutesWatched"},
                ],
                "rows": [
                    ["vid_AAA", "YT_SEARCH", 100, 300.0],
                    ["vid_AAA", "SUGGESTED", 50, 120.0],
                    ["vid_AAA", "BROWSE", 30, 90.0],
                    ["vid_BBB", "YT_SEARCH", 200, 600.0],
                    ["vid_BBB", "EXT_URL", 10, 25.0],
                ],
            }

    class FakeReports:
        def query(self, **kwargs):
            return FakeQuery()

    class FakeAnalytics:
        def reports(self):
            return FakeReports()

    return FakeAnalytics()


def make_video_df():
    """Create a minimal video metadata DataFrame matching the fetcher's format."""
    return pd.DataFrame(
        {
            "video_id": ["vid_AAA", "vid_BBB"],
            "title": ["How to Use Lightroom", "Canon R5 Review"],
            "published_at": ["2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z"],
            "duration_sec": [600, 900],
        }
    )


class TestFetchTrafficSources:
    def test_returns_dataframe_with_expected_columns(self):
        analytics = make_fake_analytics()
        video_df = make_video_df()
        video_ids = video_df["video_id"].tolist()

        result = fetch_traffic_sources(
            analytics, video_ids, "2020-01-01", "2026-04-30", video_df
        )

        assert isinstance(result, pd.DataFrame)
        expected_cols = [
            "Video",
            "Video title",
            "Traffic source",
            "Views",
            "Watch time (hours)",
        ]
        assert list(result.columns) == expected_cols

    def test_video_titles_are_joined_correctly(self):
        analytics = make_fake_analytics()
        video_df = make_video_df()
        video_ids = video_df["video_id"].tolist()

        result = fetch_traffic_sources(
            analytics, video_ids, "2020-01-01", "2026-04-30", video_df
        )

        aaa_rows = result[result["Video"] == "vid_AAA"]
        assert (aaa_rows["Video title"] == "How to Use Lightroom").all()

        bbb_rows = result[result["Video"] == "vid_BBB"]
        assert (bbb_rows["Video title"] == "Canon R5 Review").all()

    def test_watch_time_converted_to_hours(self):
        analytics = make_fake_analytics()
        video_df = make_video_df()
        video_ids = video_df["video_id"].tolist()

        result = fetch_traffic_sources(
            analytics, video_ids, "2020-01-01", "2026-04-30", video_df
        )

        # First row: vid_AAA, YT_SEARCH, 300 minutes = 5.0 hours
        yt_search_aaa = result[
            (result["Video"] == "vid_AAA") & (result["Traffic source"] == "YT_SEARCH")
        ]
        assert len(yt_search_aaa) == 1
        assert yt_search_aaa.iloc[0]["Watch time (hours)"] == pytest.approx(5.0)

    def test_views_are_integers(self):
        analytics = make_fake_analytics()
        video_df = make_video_df()
        video_ids = video_df["video_id"].tolist()

        result = fetch_traffic_sources(
            analytics, video_ids, "2020-01-01", "2026-04-30", video_df
        )

        assert result["Views"].dtype in ("int64", "int32")

    def test_all_rows_present(self):
        analytics = make_fake_analytics()
        video_df = make_video_df()
        video_ids = video_df["video_id"].tolist()

        result = fetch_traffic_sources(
            analytics, video_ids, "2020-01-01", "2026-04-30", video_df
        )

        # 3 rows for vid_AAA + 2 rows for vid_BBB = 5 total
        assert len(result) == 5
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
uv run python -m pytest tests/test_fetch_traffic_sources.py -v
```

Expected: `ImportError: cannot import name 'fetch_traffic_sources' from 'scripts.fetch_youtube_data'`

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: add failing tests for traffic source fetching"
```

---

### Task 2: Implement `fetch_traffic_sources()`

**Files:**
- Modify: `scripts/fetch_youtube_data.py` (add function after `fetch_channel_totals`, around line 160)

- [ ] **Step 1: Add the `fetch_traffic_sources` function**

Add this function after `fetch_channel_totals()` and before `def main():` in `scripts/fetch_youtube_data.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
uv run python -m pytest tests/test_fetch_traffic_sources.py -v
```

Expected: All 5 tests PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/fetch_youtube_data.py
git commit -m "feat: add fetch_traffic_sources function"
```

---

### Task 3: Wire Traffic Sources into `main()`

**Files:**
- Modify: `scripts/fetch_youtube_data.py` (modify `main()` function)

- [ ] **Step 1: Update step numbering and add traffic sources fetch**

In `main()`, update the print messages to use `[1/5]` through `[4/5]` for existing steps, then add the traffic sources fetch as step `[5/5]`.

Find these lines in `main()`:

```python
    # ── Fetch video list ──
    print("\n[1/4] Fetching video list...")
```

Change `[1/4]` to `[1/5]`.

Find:
```python
    # ── Fetch per-video analytics ──
    print("\n[2/4] Fetching per-video lifetime analytics...")
```

Change `[2/4]` to `[2/5]`.

Find:
```python
    # ── Fetch daily video breakdown ──
    print("\n[3/4] Fetching daily video breakdown...")
```

Change `[3/4]` to `[3/5]`.

Find:
```python
    # ── Fetch channel totals ──
    print("\n[4/4] Fetching channel daily totals...")
```

Change `[4/4]` to `[4/5]`.

Then add the following block **after** the channel totals section (after `print(f"      Saved: {totals_path}")`) and **before** the `# ── Summary ──` section:

```python
    # ── Fetch traffic sources ──
    print("\n[5/5] Fetching traffic sources...")
    traffic_df = fetch_traffic_sources(analytics, video_ids, start_date, end_date, video_df)
    print(f"      Fetched {len(traffic_df)} traffic source records")

    traffic_path = output_dir / "Traffic sources.csv"
    traffic_df.to_csv(traffic_path, index=False)
    print(f"      Saved: {traffic_path}")
```

- [ ] **Step 2: Verify the script still parses correctly**

```bash
uv run python -c "import scripts.fetch_youtube_data; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/fetch_youtube_data.py
git commit -m "feat: wire traffic sources into main fetch pipeline"
```

---

### Task 4: Add Integration Test for Empty API Response

**Files:**
- Modify: `tests/test_fetch_traffic_sources.py`

- [ ] **Step 1: Write test for empty response handling**

Add this test class to `tests/test_fetch_traffic_sources.py`:

```python
def make_empty_analytics():
    """Analytics service that returns no rows."""

    class FakeQuery:
        def execute(self):
            return {
                "columnHeaders": [
                    {"name": "video"},
                    {"name": "insightTrafficSourceType"},
                    {"name": "views"},
                    {"name": "estimatedMinutesWatched"},
                ],
                "rows": [],
            }

    class FakeReports:
        def query(self, **kwargs):
            return FakeQuery()

    class FakeAnalytics:
        def reports(self):
            return FakeReports()

    return FakeAnalytics()


class TestFetchTrafficSourcesEdgeCases:
    def test_empty_response_returns_empty_dataframe_with_columns(self):
        analytics = make_empty_analytics()
        video_df = make_video_df()
        video_ids = video_df["video_id"].tolist()

        result = fetch_traffic_sources(
            analytics, video_ids, "2020-01-01", "2026-04-30", video_df
        )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0
        assert list(result.columns) == [
            "Video",
            "Video title",
            "Traffic source",
            "Views",
            "Watch time (hours)",
        ]
```

- [ ] **Step 2: Run all tests**

```bash
uv run python -m pytest tests/test_fetch_traffic_sources.py -v
```

Expected: All 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_fetch_traffic_sources.py
git commit -m "test: add edge case test for empty traffic source response"
```

---

### Task 5: Update SKILL.md Documentation

**Files:**
- Modify: `.pi/skills/analyzing-youtube-analytics/SKILL.md`

- [ ] **Step 1: Update the "What's fetched" section**

In `.pi/skills/analyzing-youtube-analytics/SKILL.md`, find:

```markdown
**What's fetched:**
- Per-video lifetime metrics (views, watch time, retention, likes, comments, shares, subscribers)
- Daily video breakdowns
- Channel-level daily totals
```

Replace with:

```markdown
**What's fetched:**
- Per-video lifetime metrics (views, watch time, retention, likes, comments, shares, subscribers)
- Daily video breakdowns
- Channel-level daily totals
- Per-video traffic sources (how viewers discover each video: search, suggested, browse, external, etc.)
```

- [ ] **Step 2: Update the "If using API" data files list**

Find:

```markdown
**If using API:** Data is auto-saved to `data/api_fetch_<timestamp>/` with these files:
- `Table data.csv` — per-video lifetime summary
- `Chart data.csv` — daily breakdown per video
- `Totals.csv` — channel-level daily totals
```

Replace with:

```markdown
**If using API:** Data is auto-saved to `data/api_fetch_<timestamp>/` with these files:
- `Table data.csv` — per-video lifetime summary
- `Chart data.csv` — daily breakdown per video
- `Totals.csv` — channel-level daily totals
- `Traffic sources.csv` — per-video traffic source breakdown (search, suggested, browse, etc.)
```

- [ ] **Step 3: Commit**

```bash
git add .pi/skills/analyzing-youtube-analytics/SKILL.md
git commit -m "docs: document traffic sources in skill file"
```

---

### Task 6: Manual Smoke Test

- [ ] **Step 1: Run the full fetcher against the real API**

```bash
uv run python scripts/fetch_youtube_data.py
```

Expected output includes:
```
[5/5] Fetching traffic sources...
      Fetched <N> traffic source records
      Saved: data/api_fetch_<timestamp>/Traffic sources.csv
```

- [ ] **Step 2: Inspect the output CSV**

```bash
head -20 data/latest/Traffic\ sources.csv
```

Verify:
- Header row: `Video,Video title,Traffic source,Views,Watch time (hours)`
- Data rows have real video IDs, titles, source types like `YT_SEARCH`, `SUGGESTED`, `BROWSE`, etc.
- Watch time values are in hours (small decimals, not large minute values)
- No empty `Video title` columns

- [ ] **Step 3: Run the full test suite one final time**

```bash
uv run python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: traffic source fetching complete and verified"
```
