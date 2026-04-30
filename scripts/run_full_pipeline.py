#!/usr/bin/env python3
"""
One-command pipeline: Fetch YouTube data via API + run analysis.

Usage:
    uv run python scripts/run_full_pipeline.py
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path.cwd()

def run(cmd, cwd=None):
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False, cwd=cwd or PROJECT_ROOT)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    return result

print("=" * 60)
print("YouTube Analytics Full Pipeline")
print("=" * 60)

# Step 1: Fetch data from API
print("\n[Step 1/2] Fetching data from YouTube Analytics API...")
run(["uv", "run", "python", "scripts/fetch_youtube_data.py"])

# Step 2: Run analysis (auto-detects latest data)
print("\n[Step 2/2] Running analysis...")
run(["uv", "run", "python", "scripts/youtube_analytics.py"])

print("\n" + "=" * 60)
print("Pipeline complete!")
print("=" * 60)
