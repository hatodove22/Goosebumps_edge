#!/usr/bin/env python3
"""ROI / dataset utilities for analysis scripts.

This module is dependency-light (numpy + pillow only) so it can run in the same
Python environment as the Collector.

Assumptions
- Frames are stored as JPEG files referenced by frames.csv (schema v1.x).
- ROI is a fixed-center square (same as Collector default).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
from PIL import Image


@dataclass
class FrameRow:
    frame_id: int
    pc_rx_ts_ms: int
    filename: str  # relative to session_dir


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_meta(session_dir: Path) -> Dict[str, Any]:
    return read_json(session_dir / "meta.json")


def get_roi_size(meta: Dict[str, Any], default: int = 160) -> int:
    try:
        return int(meta.get("roi", {}).get("size_px", default))
    except Exception:
        return int(default)


def iter_frames(session_dir: Path) -> List[FrameRow]:
    """Load frames.csv and return a sorted list of non-dropped frames."""
    frames_csv = session_dir / "frames.csv"
    if not frames_csv.exists():
        raise FileNotFoundError(f"frames.csv not found: {frames_csv}")

    out: List[FrameRow] = []
    with frames_csv.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                if int(row.get("drop_flag", "0")) == 1:
                    continue
                filename = (row.get("filename") or "").strip()
                if not filename:
                    continue
                out.append(
                    FrameRow(
                        frame_id=int(row["frame_id"]),
                        pc_rx_ts_ms=int(row["pc_rx_ts_ms"]),
                        filename=filename,
                    )
                )
            except Exception:
                continue
    out.sort(key=lambda x: x.pc_rx_ts_ms)
    return out


def load_quality_map(session_dir: Path) -> Dict[int, Dict[str, Any]]:
    """Return dict: frame_id -> quality row (values kept as strings)."""
    q_csv = session_dir / "quality.csv"
    if not q_csv.exists():
        return {}
    out: Dict[int, Dict[str, Any]] = {}
    with q_csv.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                fid = int(row["frame_id"])
            except Exception:
                continue
            out[fid] = dict(row)
    return out


def load_labels_map(session_dir: Path) -> Dict[int, Dict[str, Any]]:
    """Return dict: frame_id -> labels row (values kept as strings)."""
    lab_csv = session_dir / "labels.csv"
    if not lab_csv.exists():
        return {}
    out: Dict[int, Dict[str, Any]] = {}
    with lab_csv.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                fid = int(row["frame_id"])
            except Exception:
                continue
            out[fid] = dict(row)
    return out


def load_roi_gray(
    jpeg_path: Path,
    roi_size: int,
    out_size: Optional[int] = None,
) -> np.ndarray:
    """Load JPEG, convert to grayscale, and crop fixed-center square ROI.

    Args:
        jpeg_path: absolute path to JPEG.
        roi_size: ROI side length in pixels (before optional resizing).
        out_size: If set, resize ROI to out_size x out_size.

    Returns:
        roi: uint8 grayscale image with shape (S, S)
    """
    img = Image.open(jpeg_path).convert("L")
    W, H = img.size
    S = int(max(8, min(roi_size, W, H)))
    x0 = max(0, (W - S) // 2)
    y0 = max(0, (H - S) // 2)
    roi = img.crop((x0, y0, x0 + S, y0 + S))
    if out_size is not None and int(out_size) != S:
        roi = roi.resize((int(out_size), int(out_size)), resample=Image.BILINEAR)
    return np.asarray(roi, dtype=np.uint8)
