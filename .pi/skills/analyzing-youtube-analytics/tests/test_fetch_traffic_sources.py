"""Tests for traffic source fetching and transformation."""

import pandas as pd
import pytest

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
