#!/usr/bin/env python3
"""
Convert events.csv (goose_on/off) into labels.csv (per-frame labels) using frames.csv timestamps.

Usage:
  python tools/make_labels.py dataset/subject_001/2026-01-15_session_01
"""
import argparse
import csv
from pathlib import Path
from typing import List, Tuple


def load_frames(frames_csv: Path):
    frames = []
    with frames_csv.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if int(row.get("drop_flag", "0")) == 1:
                continue
            frames.append({
                "frame_id": int(row["frame_id"]),
                "pc_rx_ts_ms": int(row["pc_rx_ts_ms"]),
                "filename": row["filename"],
            })
    frames.sort(key=lambda x: x["pc_rx_ts_ms"])
    return frames


def load_events(events_csv: Path):
    events = []
    with events_csv.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                events.append({
                    "pc_ts_ms": int(row["pc_ts_ms"]),
                    "type": row["type"],
                    "value": row.get("value",""),
                    "note": row.get("note",""),
                })
            except Exception:
                pass
    events.sort(key=lambda x: x["pc_ts_ms"])
    return events


def intervals(events, on_type: str, off_type: str) -> List[Tuple[int,int]]:
    on_stack = []
    out = []
    for e in events:
        if e["type"] == on_type:
            on_stack.append(e["pc_ts_ms"])
        elif e["type"] == off_type and on_stack:
            t0 = on_stack.pop(0)
            t1 = e["pc_ts_ms"]
            if t1 > t0:
                out.append((t0,t1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir", type=str)
    args = ap.parse_args()
    sdir = Path(args.session_dir)
    frames_csv = sdir / "frames.csv"
    events_csv = sdir / "events.csv"
    if not frames_csv.exists() or not events_csv.exists():
        raise SystemExit("frames.csv/events.csv not found")

    frames = load_frames(frames_csv)
    events = load_events(events_csv)
    ints = intervals(events, "goose_on", "goose_off")

    def in_any(t: int) -> int:
        for a,b in ints:
            if a <= t <= b:
                return 1
        return 0

    out_path = sdir / "labels.csv"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["frame_id","pc_rx_ts_ms","filename","piloerection","use_flag","note"])
        w.writeheader()
        for fr in frames:
            y = in_any(fr["pc_rx_ts_ms"])
            w.writerow({
                "frame_id": fr["frame_id"],
                "pc_rx_ts_ms": fr["pc_rx_ts_ms"],
                "filename": fr["filename"],
                "piloerection": y,
                "use_flag": 1,
                "note": "",
            })
    print("wrote", out_path)

if __name__ == "__main__":
    main()
