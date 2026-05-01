"""Tests for geography fetching and transformation."""

import pandas as pd
import pytest

from scripts.fetch_youtube_data import fetch_geography


def make_fake_analytics():
    class FakeQuery:
        def execute(self):
            return {
                "columnHeaders": [
                    {"name": "video"},
                    {"name": "country"},
                    {"name": "views"},
                    {"name": "estimatedMinutesWatched"},
                    {"name": "subscribersGained"},
                ],
                "rows": [
                    ["vid_AAA", "US", 500, 1500.0, 10],
                    ["vid_AAA", "IN", 300, 600.0, 5],
                    ["vid_BBB", "US", 200, 800.0, 3],
                    ["vid_BBB", "GB", 100, 300.0, 2],
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
        "video_id": ["vid_AAA", "vid_BBB"],
        "title": ["How to Use Lightroom", "Canon R5 Review"],
        "published_at": ["2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z"],
        "duration_sec": [600, 900],
    })


class TestFetchGeography:
    def test_returns_dataframe_with_expected_columns(self):
        result = fetch_geography(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert list(result.columns) == [
            "Video", "Video title", "Country", "Views",
            "Watch time (hours)", "Subscribers gained",
        ]

    def test_video_titles_joined(self):
        result = fetch_geography(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert (result[result["Video"] == "vid_AAA"]["Video title"] == "How to Use Lightroom").all()

    def test_watch_time_converted_to_hours(self):
        result = fetch_geography(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        us_aaa = result[(result["Video"] == "vid_AAA") & (result["Country"] == "US")]
        assert us_aaa.iloc[0]["Watch time (hours)"] == pytest.approx(25.0)

    def test_all_rows_present(self):
        result = fetch_geography(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert len(result) == 4

    def test_empty_response(self):
        class FakeQuery:
            def execute(self):
                return {"columnHeaders": [
                    {"name": "video"}, {"name": "country"},
                    {"name": "views"}, {"name": "estimatedMinutesWatched"},
                    {"name": "subscribersGained"},
                ], "rows": []}

        class FakeReports:
            def query(self, **kwargs):
                return FakeQuery()

        class FakeAnalytics:
            def reports(self):
                return FakeReports()

        result = fetch_geography(
            FakeAnalytics(), ["vid_AAA"], "2020-01-01", "2026-04-30", make_video_df()
        )
        assert len(result) == 0
        assert list(result.columns) == [
            "Video", "Video title", "Country", "Views",
            "Watch time (hours)", "Subscribers gained",
        ]
