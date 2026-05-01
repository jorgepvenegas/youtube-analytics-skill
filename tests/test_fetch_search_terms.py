"""Tests for search term fetching and transformation."""

import pandas as pd
import pytest

from scripts.fetch_youtube_data import fetch_search_terms


def make_fake_analytics():
    """Create a mock analytics service that returns canned search term data."""

    class FakeQuery:
        def execute(self):
            return {
                "columnHeaders": [
                    {"name": "video"},
                    {"name": "insightTrafficSourceDetail"},
                    {"name": "views"},
                    {"name": "estimatedMinutesWatched"},
                ],
                "rows": [
                    ["vid_AAA", "lightroom tutorial", 80, 240.0],
                    ["vid_AAA", "how to edit photos", 20, 60.0],
                    ["vid_BBB", "canon r5 review", 150, 450.0],
                    ["vid_BBB", "canon r5 vs r6", 50, 100.0],
                ],
            }

    class FakeReports:
        def query(self, **kwargs):
            # Verify the YT_SEARCH filter is being passed
            assert "insightTrafficSourceType==YT_SEARCH" in kwargs.get("filters", "")
            return FakeQuery()

    class FakeAnalytics:
        def reports(self):
            return FakeReports()

    return FakeAnalytics()


def make_video_df():
    """Create a minimal video metadata DataFrame."""
    return pd.DataFrame(
        {
            "video_id": ["vid_AAA", "vid_BBB"],
            "title": ["How to Use Lightroom", "Canon R5 Review"],
            "published_at": ["2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z"],
            "duration_sec": [600, 900],
        }
    )


class TestFetchSearchTerms:
    def test_returns_dataframe_with_expected_columns(self):
        analytics = make_fake_analytics()
        video_df = make_video_df()
        video_ids = video_df["video_id"].tolist()

        result = fetch_search_terms(
            analytics, video_ids, "2020-01-01", "2026-04-30", video_df
        )

        assert isinstance(result, pd.DataFrame)
        expected_cols = [
            "Video",
            "Video title",
            "Search term",
            "Views",
            "Watch time (hours)",
        ]
        assert list(result.columns) == expected_cols

    def test_video_titles_are_joined_correctly(self):
        analytics = make_fake_analytics()
        video_df = make_video_df()
        video_ids = video_df["video_id"].tolist()

        result = fetch_search_terms(
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

        result = fetch_search_terms(
            analytics, video_ids, "2020-01-01", "2026-04-30", video_df
        )

        # vid_AAA "lightroom tutorial": 240 minutes = 4.0 hours
        row = result[
            (result["Video"] == "vid_AAA")
            & (result["Search term"] == "lightroom tutorial")
        ]
        assert len(row) == 1
        assert row.iloc[0]["Watch time (hours)"] == pytest.approx(4.0)

    def test_views_are_integers(self):
        analytics = make_fake_analytics()
        video_df = make_video_df()
        video_ids = video_df["video_id"].tolist()

        result = fetch_search_terms(
            analytics, video_ids, "2020-01-01", "2026-04-30", video_df
        )

        assert result["Views"].dtype in ("int64", "int32")

    def test_all_rows_present(self):
        analytics = make_fake_analytics()
        video_df = make_video_df()
        video_ids = video_df["video_id"].tolist()

        result = fetch_search_terms(
            analytics, video_ids, "2020-01-01", "2026-04-30", video_df
        )

        assert len(result) == 4


def make_empty_analytics():
    """Analytics service that returns no rows."""

    class FakeQuery:
        def execute(self):
            return {
                "columnHeaders": [
                    {"name": "video"},
                    {"name": "insightTrafficSourceDetail"},
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


class TestFetchSearchTermsEdgeCases:
    def test_empty_response_returns_empty_dataframe_with_columns(self):
        analytics = make_empty_analytics()
        video_df = make_video_df()
        video_ids = video_df["video_id"].tolist()

        result = fetch_search_terms(
            analytics, video_ids, "2020-01-01", "2026-04-30", video_df
        )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0
        assert list(result.columns) == [
            "Video",
            "Video title",
            "Search term",
            "Views",
            "Watch time (hours)",
        ]
