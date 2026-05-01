"""Tests for content type fetching and transformation."""

import pandas as pd
import pytest

from scripts.fetch_youtube_data import fetch_content_type


def make_fake_analytics():
    class FakeQuery:
        def execute(self):
            return {
                "columnHeaders": [
                    {"name": "video"},
                    {"name": "creatorContentType"},
                    {"name": "views"},
                    {"name": "estimatedMinutesWatched"},
                    {"name": "averageViewPercentage"},
                    {"name": "subscribersGained"},
                ],
                "rows": [
                    ["vid_AAA", "videoOnDemand", 1000, 3000.0, 65.5, 20],
                    ["vid_BBB", "short", 5000, 500.0, 90.0, 5],
                    ["vid_CCC", "liveStream", 200, 1200.0, 30.0, 8],
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
    return pd.DataFrame({
        "video_id": ["vid_AAA", "vid_BBB", "vid_CCC"],
        "title": ["How to Use Lightroom", "Quick CSS Tip", "Live Q&A"],
        "published_at": ["2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z", "2025-03-01T00:00:00Z"],
        "duration_sec": [600, 30, 3600],
    })


class TestFetchContentType:
    def test_returns_dataframe_with_expected_columns(self):
        result = fetch_content_type(
            make_fake_analytics(), ["vid_AAA", "vid_BBB", "vid_CCC"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert list(result.columns) == [
            "Video", "Video title", "Content type", "Views",
            "Watch time (hours)", "Avg % viewed", "Subscribers gained",
        ]

    def test_video_titles_joined(self):
        result = fetch_content_type(
            make_fake_analytics(), ["vid_AAA", "vid_BBB", "vid_CCC"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert result[result["Video"] == "vid_BBB"].iloc[0]["Video title"] == "Quick CSS Tip"

    def test_watch_time_converted_to_hours(self):
        result = fetch_content_type(
            make_fake_analytics(), ["vid_AAA", "vid_BBB", "vid_CCC"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        vod = result[result["Video"] == "vid_AAA"]
        # 3000 minutes / 60 = 50.0 hours
        assert vod.iloc[0]["Watch time (hours)"] == pytest.approx(50.0)

    def test_content_types_preserved(self):
        result = fetch_content_type(
            make_fake_analytics(), ["vid_AAA", "vid_BBB", "vid_CCC"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        types = set(result["Content type"])
        assert types == {"videoOnDemand", "short", "liveStream"}

    def test_all_rows_present(self):
        result = fetch_content_type(
            make_fake_analytics(), ["vid_AAA", "vid_BBB", "vid_CCC"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert len(result) == 3

    def test_empty_response(self):
        class FakeQuery:
            def execute(self):
                return {"columnHeaders": [
                    {"name": "video"}, {"name": "creatorContentType"},
                    {"name": "views"}, {"name": "estimatedMinutesWatched"},
                    {"name": "averageViewPercentage"}, {"name": "subscribersGained"},
                ], "rows": []}

        class FakeReports:
            def query(self, **kwargs):
                return FakeQuery()

        class FakeAnalytics:
            def reports(self):
                return FakeReports()

        result = fetch_content_type(
            FakeAnalytics(), ["vid_AAA"], "2020-01-01", "2026-04-30", make_video_df()
        )
        assert len(result) == 0
        assert list(result.columns) == [
            "Video", "Video title", "Content type", "Views",
            "Watch time (hours)", "Avg % viewed", "Subscribers gained",
        ]
