#!/usr/bin/env python3
"""
One-command pipeline: Fetch YouTube data via API + run analysis + serve web report.

Usage:
    uv run python scripts/run_full_pipeline.py           # Full pipeline with web report
    uv run python scripts/run_full_pipeline.py --text    # Skip web report, text only
    uv run python scripts/run_full_pipeline.py --port 8080
"""

import argparse
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description="YouTube Analytics Full Pipeline")
parser.add_argument("--text", action="store_true", help="Skip web report, output text analysis only")
parser.add_argument("--port", type=int, default=8765, help="Port for web report server")
parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
args = parser.parse_args()

PROJECT_ROOT = Path.cwd()

def run(cmd, cwd=None):
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False, cwd=cwd or PROJECT_ROOT)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    return result

steps = 2 if args.text else 3

print("=" * 60)
print("YouTube Analytics Full Pipeline")
print("=" * 60)

# Step 1: Fetch data from API
print(f"\n[Step 1/{steps}] Fetching data from YouTube Analytics API...")
run(["uv", "run", "python", "scripts/fetch_youtube_data.py"])

# Step 2: Run text analysis
print(f"\n[Step 2/{steps}] Running text analysis...")
run(["uv", "run", "python", "scripts/youtube_analytics.py"])

# Step 3: Generate and serve web report
if not args.text:
    print(f"\n[Step 3/{steps}] Generating interactive web report...")
    serve_cmd = ["uv", "run", "python", "scripts/serve_report.py", "--port", str(args.port)]
    if args.no_open:
        serve_cmd.append("--no-open")
    run(serve_cmd)

print("\n" + "=" * 60)
print("Pipeline complete!")
print("=" * 60)
