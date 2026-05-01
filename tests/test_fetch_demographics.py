"""Tests for demographics fetching and transformation."""

import pandas as pd
import pytest

from scripts.fetch_youtube_data import fetch_demographics


def make_fake_analytics():
    class FakeQuery:
        def execute(self):
            return {
                "columnHeaders": [
                    {"name": "video"},
                    {"name": "ageGroup"},
                    {"name": "gender"},
                    {"name": "viewerPercentage"},
                ],
                "rows": [
                    ["vid_AAA", "age25-34", "male", 35.5],
                    ["vid_AAA", "age25-34", "female", 15.2],
                    ["vid_AAA", "age18-24", "male", 20.0],
                    ["vid_BBB", "age35-44", "male", 40.0],
                    ["vid_BBB", "age25-34", "female", 25.0],
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


class TestFetchDemographics:
    def test_returns_dataframe_with_expected_columns(self):
        result = fetch_demographics(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert list(result.columns) == [
            "Video", "Video title", "Age group", "Gender", "Viewer %",
        ]

    def test_video_titles_joined(self):
        result = fetch_demographics(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert (result[result["Video"] == "vid_AAA"]["Video title"] == "How to Use Lightroom").all()

    def test_viewer_percentage_preserved(self):
        result = fetch_demographics(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        row = result[
            (result["Video"] == "vid_AAA")
            & (result["Age group"] == "age25-34")
            & (result["Gender"] == "male")
        ]
        assert row.iloc[0]["Viewer %"] == pytest.approx(35.5)

    def test_all_rows_present(self):
        result = fetch_demographics(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert len(result) == 5

    def test_empty_response(self):
        class FakeQuery:
            def execute(self):
                return {"columnHeaders": [
                    {"name": "video"}, {"name": "ageGroup"},
                    {"name": "gender"}, {"name": "viewerPercentage"},
                ], "rows": []}

        class FakeReports:
            def query(self, **kwargs):
                return FakeQuery()

        class FakeAnalytics:
            def reports(self):
                return FakeReports()

        result = fetch_demographics(
            FakeAnalytics(), ["vid_AAA"], "2020-01-01", "2026-04-30", make_video_df()
        )
        assert len(result) == 0
        assert list(result.columns) == [
            "Video", "Video title", "Age group", "Gender", "Viewer %",
        ]
