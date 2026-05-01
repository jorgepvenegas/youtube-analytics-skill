"""Tests for retention curve fetching and transformation."""

import pandas as pd
import pytest

from scripts.fetch_youtube_data import fetch_retention_curves


def make_fake_analytics(responses=None):
    """Create a mock analytics service.

    Args:
        responses: dict mapping video_id to rows. If None, uses defaults.
    """
    if responses is None:
        responses = {
            "vid_AAA": [
                [0.0, 1.0, 1.2],
                [0.25, 0.85, 1.1],
                [0.5, 0.60, 0.95],
                [0.75, 0.40, 0.8],
                [1.0, 0.20, 0.7],
            ],
            "vid_BBB": [
                [0.0, 1.0, 0.9],
                [0.5, 0.50, 0.8],
                [1.0, 0.10, 0.6],
            ],
        }

    class FakeQuery:
        def __init__(self, video_id):
            self.video_id = video_id

        def execute(self):
            rows = responses.get(self.video_id, [])
            return {
                "columnHeaders": [
                    {"name": "elapsedVideoTimeRatio"},
                    {"name": "audienceWatchRatio"},
                    {"name": "relativeRetentionPerformance"},
                ],
                "rows": rows,
            }

    class FakeReports:
        def query(self, **kwargs):
            # Extract video ID from filter like "video==vid_AAA;audienceType==ORGANIC"
            filters = kwargs.get("filters", "")
            video_id = filters.split(";")[0].split("==")[1]
            return FakeQuery(video_id)

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


class TestFetchRetentionCurves:
    def test_returns_dataframe_with_expected_columns(self):
        result = fetch_retention_curves(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert list(result.columns) == [
            "Video", "Video title", "Elapsed ratio",
            "Audience watch ratio", "Relative retention",
        ]

    def test_video_titles_joined(self):
        result = fetch_retention_curves(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        aaa_rows = result[result["Video"] == "vid_AAA"]
        assert (aaa_rows["Video title"] == "How to Use Lightroom").all()

    def test_all_rows_from_both_videos_merged(self):
        result = fetch_retention_curves(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        # vid_AAA has 5 points, vid_BBB has 3 = 8 total
        assert len(result) == 8

    def test_retention_values_preserved(self):
        result = fetch_retention_curves(
            make_fake_analytics(), ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        row = result[
            (result["Video"] == "vid_AAA") & (result["Elapsed ratio"] == 0.5)
        ]
        assert len(row) == 1
        assert row.iloc[0]["Audience watch ratio"] == pytest.approx(0.60)
        assert row.iloc[0]["Relative retention"] == pytest.approx(0.95)

    def test_video_with_no_data_is_skipped(self):
        analytics = make_fake_analytics(responses={
            "vid_AAA": [
                [0.0, 1.0, 1.0],
                [1.0, 0.5, 0.9],
            ],
            "vid_BBB": [],  # no data
        })
        result = fetch_retention_curves(
            analytics, ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert len(result) == 2
        assert set(result["Video"]) == {"vid_AAA"}

    def test_empty_all_videos(self):
        analytics = make_fake_analytics(responses={
            "vid_AAA": [],
            "vid_BBB": [],
        })
        result = fetch_retention_curves(
            analytics, ["vid_AAA", "vid_BBB"],
            "2020-01-01", "2026-04-30", make_video_df()
        )
        assert len(result) == 0
        assert list(result.columns) == [
            "Video", "Video title", "Elapsed ratio",
            "Audience watch ratio", "Relative retention",
        ]
