#!/usr/bin/env python3
"""
One-command pipeline: Fetch YouTube data via API + run analysis + serve web report.
Optionally launches an async researcher agent for deep analysis.

Usage:
    uv run python scripts/run_full_pipeline.py           # Full pipeline with web report + researcher
    uv run python scripts/run_full_pipeline.py --text    # Skip web report, text only
    uv run python scripts/run_full_pipeline.py --no-research  # Skip researcher
    uv run python scripts/run_full_pipeline.py --port 8080
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser(description="YouTube Analytics Full Pipeline")
parser.add_argument("--text", action="store_true", help="Skip web report, output text analysis only")
parser.add_argument("--no-research", action="store_true", help="Skip async researcher agent")
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

def run_bg(cmd, cwd=None):
    """Run a command in the background, return the process handle."""
    print(f"\n$ {' '.join(cmd)} [background]")
    return subprocess.Popen(cmd, cwd=cwd or PROJECT_ROOT)

def get_latest_data_dir():
    """Find the most recently created data directory."""
    data_dir = PROJECT_ROOT / "data"
    if not data_dir.exists():
        return None
    candidates = [d for d in data_dir.iterdir() if d.is_dir() and d.name != "latest"]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]

steps = 2 if args.text else 3
if not args.no_research and not args.text:
    steps = 4

print("=" * 60)
print("YouTube Analytics Full Pipeline")
print("=" * 60)

# Step 1: Fetch data from API
print(f"\n[Step 1/{steps}] Fetching data from YouTube Analytics API...")
run(["uv", "run", "python", "scripts/fetch_youtube_data.py"])

# Resolve the data directory that was just created
latest_data = get_latest_data_dir()
if latest_data is None:
    # Fall back to data/latest symlink
    latest_link = PROJECT_ROOT / "data" / "latest"
    if latest_link.exists():
        latest_data = latest_link.resolve()
    else:
        print("ERROR: Could not find fetched data directory.")
        sys.exit(1)

data_dir_str = str(latest_data.relative_to(PROJECT_ROOT))
ts = latest_data.name.replace("api_fetch_", "") if "api_fetch_" in latest_data.name else None

# Step 2: Run text analysis
print(f"\n[Step 2/{steps}] Running text analysis...")
run(["uv", "run", "python", "scripts/youtube_analytics.py", "--data-dir", data_dir_str])

# Step 3: Start web server in background
server_proc = None
if not args.text:
    print(f"\n[Step 3/{steps}] Starting web server in background...")
    serve_cmd = ["uv", "run", "python", "scripts/serve_report.py", "--data-dir", data_dir_str, "--port", str(args.port)]
    if args.no_open:
        serve_cmd.append("--no-open")
    server_proc = run_bg(serve_cmd)
    time.sleep(2)  # Give server time to start
    print(f"Server running at: http://127.0.0.1:{args.port}/report.html")

# Step 4: Launch async researcher
if not args.no_research and not args.text:
    print(f"\n[Step 4/{steps}] Launching async researcher agent...")
    researcher_cmd = [
        "uv", "run", "python", "scripts/researcher.py",
        "--data-dir", data_dir_str,
        "--timestamp", ts or "",
    ]
    researcher_proc = run_bg(researcher_cmd)
    print(f"Researcher running in background.")
    print(f"Research report will appear at: reports/research_{ts or '<timestamp>'}.md")

print("\n" + "=" * 60)
if server_proc:
    print("Pipeline complete! Server is running.")
    print(f"View raw data: http://127.0.0.1:{args.port}/report.html")
    if not args.no_research:
        print(f"Research report: reports/research_{ts or '<timestamp>'}.md")
    print("Press Ctrl+C to stop the server.")
    try:
        server_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server_proc.terminate()
        server_proc.wait()
        # Also terminate researcher if running
        if not args.no_research and 'researcher_proc' in locals():
            print("Stopping researcher...")
            researcher_proc.terminate()
            researcher_proc.wait()
else:
    print("Pipeline complete!")
print("=" * 60)
