"""Tests for device type fetching and transformation."""

import pandas as pd
import pytest

from scripts.fetch_youtube_data import fetch_device_type


def make_fake_analytics():
    class FakeQuery:
        def execute(self):
            return {
                "columnHeaders": [
                    {"name": "video"},
                    {"name": "deviceType"},
                    {"name": "views"},
                    {"name": "estimatedMinutesWatched"},
                ],
                "rows": [
                    ["vid_AAA", "MOBILE", 400, 800.0],
                    ["vid_AAA", "DESKTOP", 200, 600.0],
                    ["vid_AAA", "TV", 50, 300.0],
                    ["vid_BBB", "MOBILE", 300, 500.0],
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


class TestFetchDeviceType:
    def test_returns_dataframe_with_expected_columns(self):
        result = fetch_device_type(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert list(result.columns) == [
            "Video", "Video title", "Device", "Views", "Watch time (hours)",
        ]

    def test_video_titles_joined(self):
        result = fetch_device_type(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert (result[result["Video"] == "vid_BBB"]["Video title"] == "Canon R5 Review").all()

    def test_watch_time_converted_to_hours(self):
        result = fetch_device_type(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        mobile_aaa = result[(result["Video"] == "vid_AAA") & (result["Device"] == "MOBILE")]
        # 800 minutes / 60 = 13.3333 hours
        assert mobile_aaa.iloc[0]["Watch time (hours)"] == pytest.approx(13.3333, abs=0.001)

    def test_all_rows_present(self):
        result = fetch_device_type(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert len(result) == 4

    def test_empty_response(self):
        class FakeQuery:
            def execute(self):
                return {"columnHeaders": [
                    {"name": "video"}, {"name": "deviceType"},
                    {"name": "views"}, {"name": "estimatedMinutesWatched"},
                ], "rows": []}

        class FakeReports:
            def query(self, **kwargs):
                return FakeQuery()

        class FakeAnalytics:
            def reports(self):
                return FakeReports()

        result = fetch_device_type(
            FakeAnalytics(), ["vid_AAA"], "2020-01-01", "2026-04-30", make_video_df()
        )
        assert len(result) == 0
        assert list(result.columns) == [
            "Video", "Video title", "Device", "Views", "Watch time (hours)",
        ]
