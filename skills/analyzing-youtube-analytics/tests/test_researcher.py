import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from scripts.researcher import load_data, compute_anomaly_flags, generate_report

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "researcher"

class TestLoadData:
    def test_loads_summary(self, tmp_path):
        # Create minimal Table data.csv
        csv = tmp_path / "Table data.csv"
        csv.write_text("""Video,Video title,Duration,Views,Watch time (hours),Subscribers gained,Subscribers lost,Likes,Dislikes,Comments added,Shares,Impressions,Impressions click-through rate (%),Average view duration,Average percentage viewed (%),Video publish time
vid1,Test Video 1,0:05:00,1000,50.0,10,2,50,1,5,2,5000,20.0,0:02:30,50.0,Jan 1 2024
vid2,Test Video 2,0:03:00,500,20.0,5,1,20,0,2,1,2000,25.0,0:01:30,50.0,Jan 2 2024
""")
        data = load_data(tmp_path)
        assert "summary" in data
        assert len(data["summary"]) == 2
        assert data["summary"]["Views"].sum() == 1500

class TestComputeAnomalyFlags:
    def test_flags_top_outlier(self):
        df = pd.DataFrame({
            "Views": [100, 102, 101, 99, 100, 103, 100, 500],
            "Video": ["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8"],
        })
        flags = compute_anomaly_flags(df, "Views")
        assert flags["v8"] == "spike"
        assert flags["v1"] == "normal"

    def test_flags_bottom_outlier(self):
        df = pd.DataFrame({
            "Views": [100, 102, 101, 99, 100, 103, 100, 5],
            "Video": ["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8"],
        })
        flags = compute_anomaly_flags(df, "Views")
        assert flags["v8"] == "drop"

class TestGenerateReport:
    def test_report_has_sections(self, tmp_path):
        summary = pd.DataFrame({
            "Video": ["v1", "v2", "v3", "v4"],
            "Video title": ["A", "B", "C", "D"],
            "Views": [1000, 500, 200, 100],
            "Watch time (hours)": [50, 25, 10, 5],
            "Duration (seconds)": [300, 180, 240, 600],
            "CTR (%)": [8.0, 5.0, 3.0, 2.0],
            "AVD ratio": [0.5, 0.4, 0.3, 0.2],
            "Engagement rate (%)": [5.0, 3.0, 2.0, 1.0],
            "Subscriber conversion rate (%)": [1.0, 0.5, 0.2, 0.1],
            "Average percentage viewed (%)": [60, 50, 40, 30],
            "Likes": [50, 20, 10, 5],
            "Comments added": [5, 2, 1, 0],
            "Shares": [2, 1, 0, 0],
            "Net subscribers": [8, 4, 2, 1],
        })
        report = generate_report(summary, data_dir=tmp_path)
        assert "## Executive Summary" in report
        assert "## What Works" in report
        assert "## What Doesn't Work" in report
        assert "## New Content Ideas" in report
