#!/usr/bin/env python3
"""Derive per-frame features from a recorded session.

This script is meant to be run AFTER data collection.
It converts the raw session (frames.csv + frames/*.jpg + quality.csv + labels.csv)
into a single, analysis-friendly CSV: derived/features.csv.

Why this exists
- Avoid GIGO: before training any ML model, check whether simple features
  can separate labeled positive/negative segments.
- Make it easy to compute summary stats (AUC, effect size) with minimal deps.

Outputs
- <session_dir>/derived/features.csv
- <session_dir>/derived/features_report.json (if labels exist)
- <session_dir>/derived/features_plot.png (optional)

Usage
  python tools/derive_features.py dataset/subject_001/2026-01-16_session_01

Tip (uv)
  cd collector
  uv run python ../tools/derive_features.py ../dataset/subject_001/2026-01-16_session_01
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Optional plotting
try:
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None

# Local helper (works even when tools/ is not a package)
import sys
THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from roi_utils import FrameRow, get_roi_size, load_labels_map, load_meta, load_quality_map, load_roi_gray, iter_frames


def gb_index_from_roi(gray_roi: np.ndarray, r_min: int, r_max: int) -> float:
    """FFT-based texture index (same core idea as collector/app/pilot_fft.py).

    - subtract mean
    - apply 2D Hann window
    - compute power spectrum
    - radial average
    - take max in [r_min, r_max]

    Notes
    - gray_roi must be square.
    - r_min/r_max are in *pixels* in the FFT shifted domain.
    """
    I = gray_roi.astype(np.float32)
    I -= float(I.mean())

    S = int(I.shape[0])
    if I.ndim != 2 or I.shape[0] != I.shape[1] or S < 8:
        return float("nan")

    w = np.hanning(S).astype(np.float32)
    window2d = np.outer(w, w)
    Iw = I * window2d

    F = np.fft.fft2(Iw)
    P = (np.abs(F) ** 2).astype(np.float32)
    P = np.fft.fftshift(P)

    cy, cx = S // 2, S // 2
    yy, xx = np.indices((S, S))
    rr = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2).astype(np.int32)

    max_r = int(rr.max())
    radial_sum = np.bincount(rr.ravel(), P.ravel(), minlength=max_r + 1).astype(np.float64)
    radial_cnt = np.bincount(rr.ravel(), minlength=max_r + 1).astype(np.float64)
    R = radial_sum / np.maximum(radial_cnt, 1.0)

    r_min = max(0, min(int(r_min), max_r))
    r_max = max(0, min(int(r_max), max_r))
    if r_max < r_min:
        r_min, r_max = r_max, r_min

    band = R[r_min : r_max + 1]
    if band.size == 0:
        return float("nan")
    return float(np.max(band))


def laplacian_var(gray: np.ndarray) -> float:
    """Variance of Laplacian (3x3 kernel)."""
    k = np.array(
        [[0, 1, 0],
         [1, -4, 1],
         [0, 1, 0]],
        dtype=np.float32,
    )
    g = gray.astype(np.float32)
    gp = np.pad(g, 1, mode="edge")
    out = (
        k[0, 0] * gp[0:-2, 0:-2] + k[0, 1] * gp[0:-2, 1:-1] + k[0, 2] * gp[0:-2, 2:]
        + k[1, 0] * gp[1:-1, 0:-2] + k[1, 1] * gp[1:-1, 1:-1] + k[1, 2] * gp[1:-1, 2:]
        + k[2, 0] * gp[2:, 0:-2] + k[2, 1] * gp[2:, 1:-1] + k[2, 2] * gp[2:, 2:]
    )
    return float(np.var(out))


def laplacian_abs_mean(gray: np.ndarray) -> float:
    """Mean absolute Laplacian magnitude (3x3 kernel)."""
    k = np.array(
        [[0, 1, 0],
         [1, -4, 1],
         [0, 1, 0]],
        dtype=np.float32,
    )
    g = gray.astype(np.float32)
    gp = np.pad(g, 1, mode="edge")
    out = (
        k[0, 0] * gp[0:-2, 0:-2] + k[0, 1] * gp[0:-2, 1:-1] + k[0, 2] * gp[0:-2, 2:]
        + k[1, 0] * gp[1:-1, 0:-2] + k[1, 1] * gp[1:-1, 1:-1] + k[1, 2] * gp[1:-1, 2:]
        + k[2, 0] * gp[2:, 0:-2] + k[2, 1] * gp[2:, 1:-1] + k[2, 2] * gp[2:, 2:]
    )
    return float(np.mean(np.abs(out)))


def banding_score(gray: np.ndarray) -> float:
    """Simple banding heuristic: Var(diff(row_mean))."""
    row_mean = gray.astype(np.float32).mean(axis=1)
    d = np.diff(row_mean)
    return float(np.var(d))


def auc_mann_whitney(y_true: np.ndarray, scores: np.ndarray) -> float:
    """ROC AUC via rank statistic (no sklearn dependency)."""
    y = y_true.astype(np.int32)
    s = scores.astype(np.float64)
    pos = (y == 1)
    neg = (y == 0)
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")

    order = np.argsort(s)
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(s) + 1, dtype=np.float64)

    # tie correction
    s_sorted = s[order]
    i = 0
    while i < len(s_sorted):
        j = i + 1
        while j < len(s_sorted) and s_sorted[j] == s_sorted[i]:
            j += 1
        if j - i > 1:
            avg_rank = float((i + 1 + j) / 2.0)
            ranks[order[i:j]] = avg_rank
        i = j

    rank_sum_pos = float(ranks[pos].sum())
    auc = (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir", type=str, help="dataset/.../<session> directory")
    ap.add_argument("--out", type=str, default="", help="output CSV path (default: <session_dir>/derived/features.csv)")
    ap.add_argument("--roi-size", type=int, default=0, help="override ROI size (default: meta.json roi.size_px or 160)")
    ap.add_argument("--roi-out-size", type=int, default=0, help="resize ROI for feature extraction (0: no resize)")
    ap.add_argument("--stride", type=int, default=1, help="use every N-th frame")
    ap.add_argument("--max-frames", type=int, default=0, help="limit frames for quick runs")
    ap.add_argument("--r-min", type=int, default=-1, help="FFT radial band min (default from meta or 8)")
    ap.add_argument("--r-max", type=int, default=-1, help="FFT radial band max (default from meta or 28)")
    ap.add_argument("--no-plot", action="store_true", help="disable plot output")
    args = ap.parse_args()

    sdir = Path(args.session_dir)
    meta = load_meta(sdir)
    frames = iter_frames(sdir)
    q_map = load_quality_map(sdir)
    lab_map = load_labels_map(sdir)

    roi_size = args.roi_size if args.roi_size > 0 else get_roi_size(meta, default=160)
    roi_out_size: Optional[int] = args.roi_out_size if args.roi_out_size > 0 else None

    # FFT band defaults
    band = meta.get("pilot_fft", {}).get("radial_band", {}) if isinstance(meta, dict) else {}
    r_min = args.r_min if args.r_min >= 0 else int(band.get("r_min", 8))
    r_max = args.r_max if args.r_max >= 0 else int(band.get("r_max", 28))

    out_csv = Path(args.out) if args.out else (sdir / "derived" / "features.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "frame_id",
        "pc_rx_ts_ms",
        "filename",
        "label_piloerection",
        "use_flag",
        "motion_flag_logged",
        "luma_mean",
        "sat_white_ratio",
        "sat_black_ratio",
        "blur_laplacian_var",
        "banding_score",
        "gb_fft_index",
        "lap_abs_mean",
        "roi_size",
        "roi_out_size",
        "fft_r_min",
        "fft_r_max",
    ]

    rows: List[Dict[str, Any]] = []

    t0 = time.time()
    used = 0
    for idx, fr in enumerate(frames):
        if args.stride > 1 and (idx % int(args.stride) != 0):
            continue
        if args.max_frames and used >= int(args.max_frames):
            break

        jpeg_path = sdir / fr.filename
        if not jpeg_path.exists():
            continue

        gray = load_roi_gray(jpeg_path, roi_size=roi_size, out_size=roi_out_size)

        luma = float(gray.mean())
        sat_w = float(np.mean(gray >= 250))
        sat_b = float(np.mean(gray <= 5))
        blur = laplacian_var(gray)
        band = banding_score(gray)
        gb = gb_index_from_roi(gray, r_min=r_min, r_max=r_max)
        lap_abs = laplacian_abs_mean(gray)

        q_row = q_map.get(fr.frame_id, {})
        motion_flag_logged = q_row.get("motion_flag", "")

        lab_row = lab_map.get(fr.frame_id, {})
        label = lab_row.get("piloerection", "")
        use_flag = lab_row.get("use_flag", "")

        rows.append(
            {
                "frame_id": fr.frame_id,
                "pc_rx_ts_ms": fr.pc_rx_ts_ms,
                "filename": fr.filename,
                "label_piloerection": label,
                "use_flag": use_flag,
                "motion_flag_logged": motion_flag_logged,
                "luma_mean": luma,
                "sat_white_ratio": sat_w,
                "sat_black_ratio": sat_b,
                "blur_laplacian_var": blur,
                "banding_score": band,
                "gb_fft_index": gb,
                "lap_abs_mean": lap_abs,
                "roi_size": int(roi_size),
                "roi_out_size": "" if roi_out_size is None else int(roi_out_size),
                "fft_r_min": int(r_min),
                "fft_r_max": int(r_max),
            }
        )
        used += 1

        if used % 200 == 0:
            dt = time.time() - t0
            print(f"processed {used} frames in {dt:.1f}s")

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)

    print("wrote", out_csv)

    # Summary report (if labels exist)
    has_labels = any((str(r.get("label_piloerection", "")).strip() in ["0", "1"]) for r in rows)
    report: Dict[str, Any] = {
        "session_dir": str(sdir),
        "out_csv": str(out_csv),
        "n_rows": int(len(rows)),
        "roi_size": int(roi_size),
        "roi_out_size": None if roi_out_size is None else int(roi_out_size),
        "fft": {"r_min": int(r_min), "r_max": int(r_max)},
        "has_labels": bool(has_labels),
    }

    if has_labels:
        y_list = []
        gb_list = []
        lap_list = []
        for r in rows:
            y_s = str(r.get("label_piloerection", "")).strip()
            if y_s not in ["0", "1"]:
                continue
            y_list.append(int(y_s))
            gb_list.append(float(r.get("gb_fft_index", float("nan"))))
            lap_list.append(float(r.get("lap_abs_mean", float("nan"))))

        y = np.asarray(y_list, dtype=np.int32)
        gb = np.asarray(gb_list, dtype=np.float32)
        lap = np.asarray(lap_list, dtype=np.float32)

        # Remove NaNs
        def _mask_valid(x: np.ndarray) -> np.ndarray:
            return np.isfinite(x)

        auc_gb = auc_mann_whitney(y[_mask_valid(gb)], gb[_mask_valid(gb)]) if int(_mask_valid(gb).sum()) > 0 else float("nan")
        auc_lap = auc_mann_whitney(y[_mask_valid(lap)], lap[_mask_valid(lap)]) if int(_mask_valid(lap).sum()) > 0 else float("nan")

        report["label_counts"] = {"pos": int((y == 1).sum()), "neg": int((y == 0).sum())}
        report["auc"] = {"gb_fft_index": float(auc_gb), "lap_abs_mean": float(auc_lap)}
        report["stats"] = {
            "gb_fft_index": {
                "pos_mean": float(np.nanmean(gb[y == 1])) if int((y == 1).sum()) > 0 else float("nan"),
                "neg_mean": float(np.nanmean(gb[y == 0])) if int((y == 0).sum()) > 0 else float("nan"),
            },
            "lap_abs_mean": {
                "pos_mean": float(np.nanmean(lap[y == 1])) if int((y == 1).sum()) > 0 else float("nan"),
                "neg_mean": float(np.nanmean(lap[y == 0])) if int((y == 0).sum()) > 0 else float("nan"),
            },
        }

        # A very simple threshold suggestion based on negative distribution
        try:
            neg = gb[y == 0]
            mu = float(np.nanmean(neg))
            sd = float(np.nanstd(neg))
            report["suggested_threshold"] = {"gb_fft_index": mu + 3.0 * sd, "k_sigma": 3.0}
        except Exception:
            pass

        out_json = out_csv.parent / "features_report.json"
        save_json(out_json, report)
        print("wrote", out_json)

        # Plot (optional)
        if (not args.no_plot) and (plt is not None) and len(rows) > 5:
            try:
                t_ms = np.asarray([int(r["pc_rx_ts_ms"]) for r in rows], dtype=np.int64)
                t_s = (t_ms - t_ms[0]).astype(np.float64) / 1000.0
                gb_all = np.asarray([float(r["gb_fft_index"]) for r in rows], dtype=np.float32)
                lap_all = np.asarray([float(r["lap_abs_mean"]) for r in rows], dtype=np.float32)
                y_all = np.asarray([
                    int(str(r.get("label_piloerection", "-1")).strip()) if str(r.get("label_piloerection", "")).strip() in ["0", "1"] else -1
                    for r in rows
                ], dtype=np.int32)

                fig = plt.figure(figsize=(10, 6))
                ax1 = fig.add_subplot(2, 1, 1)
                ax2 = fig.add_subplot(2, 1, 2)

                ax1.plot(t_s, gb_all)
                ax1.set_title("gb_fft_index (time series)")
                ax1.set_xlabel("time [s]")
                ax1.set_ylabel("gb_fft_index")

                ax2.plot(t_s, lap_all)
                ax2.set_title("lap_abs_mean (time series)")
                ax2.set_xlabel("time [s]")
                ax2.set_ylabel("lap_abs_mean")

                # Overlay label regions (best-effort)
                if np.any(y_all >= 0):
                    for ax in [ax1, ax2]:
                        ax.fill_between(t_s, ax.get_ylim()[0], ax.get_ylim()[1], where=(y_all == 1), alpha=0.15, step=None)

                fig.tight_layout()
                out_png = out_csv.parent / "features_plot.png"
                fig.savefig(out_png, dpi=150)
                plt.close(fig)
                print("wrote", out_png)
            except Exception as e:
                print("plot skipped:", e)

    else:
        # Even without labels, write a minimal report.
        out_json = out_csv.parent / "features_report.json"
        save_json(out_json, report)
        print("wrote", out_json)


if __name__ == "__main__":
    main()
