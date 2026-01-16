#!/usr/bin/env python3
"""
Validate a session folder for basic integrity.
Usage:
  python tools/validate_session.py dataset/subject_001/2026-01-15_session_01
"""
import argparse
import csv
from pathlib import Path


def count_lines(csv_path: Path) -> int:
    if not csv_path.exists():
        return 0
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        return sum(1 for _ in f) - 1  # exclude header


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir", type=str)
    args = ap.parse_args()
    sdir = Path(args.session_dir)

    required = ["meta.json", "frames.csv", "events.csv", "quality.csv"]
    missing = [x for x in required if not (sdir / x).exists()]
    if missing:
        print("MISSING:", missing)

    frames_dir = sdir / "frames"
    if not frames_dir.exists():
        print("MISSING: frames/")
    else:
        jpgs = list(frames_dir.glob("*.jpg"))
        print("frames jpg count:", len(jpgs))

    frames_csv = sdir / "frames.csv"
    n_frames_rows = count_lines(frames_csv)
    print("frames.csv rows:", n_frames_rows)

    events_csv = sdir / "events.csv"
    n_events_rows = count_lines(events_csv)
    print("events.csv rows:", n_events_rows)

    quality_csv = sdir / "quality.csv"
    n_quality_rows = count_lines(quality_csv)
    print("quality.csv rows:", n_quality_rows)

    pilot_dir = sdir / "pilot"
    if pilot_dir.exists():
        print("pilot exists:", True)
        for f in ["pilot_report.json", "pilot_plot.png", "gb_index.csv"]:
            print(" ", f, ":", (pilot_dir / f).exists())
    else:
        print("pilot exists:", False)

    # Basic check: session_start/stop
    if events_csv.exists():
        with events_csv.open("r", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            types = [row["type"] for row in r if "type" in row]
        print("has session_start:", "session_start" in types)
        print("has session_stop:", "session_stop" in types)

if __name__ == "__main__":
    main()
