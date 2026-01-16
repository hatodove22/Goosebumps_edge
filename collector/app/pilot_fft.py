from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt


def gb_index_from_roi(gray_roi: np.ndarray, r_min: int, r_max: int) -> float:
    """
    FFT-based texture index.
    - 2D Hann window
    - power spectrum
    - radial average
    - max over [r_min, r_max]
    """
    I = gray_roi.astype(np.float32)
    I -= float(I.mean())

    S = I.shape[0]
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

    r_min = max(0, min(r_min, max_r))
    r_max = max(0, min(r_max, max_r))
    if r_max < r_min:
        r_min, r_max = r_max, r_min

    band = R[r_min : r_max + 1]
    if band.size == 0:
        return float("nan")
    return float(np.max(band))


def smooth_series(x: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return x.astype(np.float32)
    # simple moving average with edge padding
    w = int(window)
    pad = w // 2
    xp = np.pad(x.astype(np.float32), (pad, pad), mode="edge")
    kernel = np.ones(w, dtype=np.float32) / w
    y = np.convolve(xp, kernel, mode="valid")
    return y.astype(np.float32)


def auc_mann_whitney(y_true: np.ndarray, scores: np.ndarray) -> float:
    """
    Compute ROC AUC using Mann-Whitney U / rank statistic.
    y_true: {0,1}
    """
    y = y_true.astype(np.int32)
    s = scores.astype(np.float64)
    pos = (y == 1)
    neg = (y == 0)
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")

    # ranks with tie handling (average rank)
    order = np.argsort(s)
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(s) + 1, dtype=np.float64)

    # tie correction: average ranks for equal scores
    # Find groups in sorted scores
    s_sorted = s[order]
    i = 0
    while i < len(s_sorted):
        j = i + 1
        while j < len(s_sorted) and s_sorted[j] == s_sorted[i]:
            j += 1
        if j - i > 1:
            avg_rank = float((i + 1 + j) / 2.0)  # average of ranks i+1..j
            ranks[order[i:j]] = avg_rank
        i = j

    rank_sum_pos = float(ranks[pos].sum())
    auc = (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


def parse_events(events_csv_path: Path) -> List[Dict[str, Any]]:
    import csv
    events = []
    if not events_csv_path.exists():
        return events
    with events_csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                events.append({
                    "pc_ts_ms": int(row["pc_ts_ms"]),
                    "type": row["type"],
                    "value": row.get("value", ""),
                    "note": row.get("note", ""),
                })
            except Exception:
                continue
    events.sort(key=lambda e: e["pc_ts_ms"])
    return events


def intervals_from_events(events: List[Dict[str, Any]], start_type: str, stop_type: str) -> List[Tuple[int, int]]:
    intervals = []
    stack = []
    for e in events:
        if e["type"] == start_type:
            stack.append(e["pc_ts_ms"])
        elif e["type"] == stop_type and stack:
            t0 = stack.pop(0)
            t1 = e["pc_ts_ms"]
            if t1 > t0:
                intervals.append((t0, t1))
    return intervals


def in_any_interval(t: int, intervals: List[Tuple[int, int]]) -> bool:
    for a, b in intervals:
        if a <= t <= b:
            return True
    return False


def count_rising_edges(t_ms: np.ndarray, binary: np.ndarray, intervals: List[Tuple[int, int]]) -> Tuple[int, float]:
    """
    Count rising edges within intervals. Return (count, duration_minutes).
    """
    if t_ms.size == 0:
        return 0, 0.0
    # duration in minutes based on union approx
    dur_ms = 0
    for a, b in intervals:
        dur_ms += max(0, b - a)
    dur_min = dur_ms / 60000.0 if dur_ms > 0 else 0.0

    # rising edges: 0->1 transitions
    edges = np.where((binary[1:] == 1) & (binary[:-1] == 0))[0] + 1
    cnt = 0
    for idx in edges:
        if in_any_interval(int(t_ms[idx]), intervals):
            cnt += 1
    return cnt, dur_min


def make_pilot_report(
    out_dir: Path,
    session_id: str,
    t_ms: np.ndarray,
    gb: np.ndarray,
    gb_smooth: np.ndarray,
    gb_binary: np.ndarray,
    threshold: Optional[float],
    events: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    # intervals
    stim_intervals = intervals_from_events(events, "stim_on", "stim_off")
    motion_intervals = intervals_from_events(events, "confound_motion_start", "confound_motion_stop")
    light_intervals = intervals_from_events(events, "confound_light_start", "confound_light_stop")

    # baseline interval from calib_start..calib_done (use first)
    calib_intervals = intervals_from_events(events, "calib_start", "calib_done")
    baseline_interval = calib_intervals[0] if calib_intervals else None

    # Build y_true for AUC: positive = inside stim_intervals, negative = inside baseline_interval (and not in stim)
    y_true = np.full_like(gb_smooth, fill_value=-1, dtype=np.int32)

    if baseline_interval:
        a, b = baseline_interval
        mask_base = (t_ms >= a) & (t_ms <= b)
        y_true[mask_base] = 0

    if stim_intervals:
        mask_pos = np.zeros_like(gb_smooth, dtype=bool)
        for a, b in stim_intervals:
            mask_pos |= (t_ms >= a) & (t_ms <= b)
        y_true[mask_pos] = 1

    valid = (y_true >= 0)
    auc = auc_mann_whitney(y_true[valid], gb_smooth[valid]) if valid.any() else float("nan")

    # baseline stability (simple)
    baseline_sd = float("nan")
    baseline_drift_per_min = float("nan")
    if baseline_interval:
        a, b = baseline_interval
        mask_base = (t_ms >= a) & (t_ms <= b)
        if mask_base.any():
            xb = gb_smooth[mask_base].astype(np.float64)
            baseline_sd = float(np.std(xb, ddof=0))
            # drift: linear fit slope per minute
            tb = (t_ms[mask_base].astype(np.float64) - float(a)) / 60000.0  # minutes
            if tb.size >= 2:
                # slope in gb units per minute
                slope = float(np.polyfit(tb, xb, deg=1)[0])
                baseline_drift_per_min = abs(slope)

    # false positives in confounds: rising edges of gb_binary
    fp_motion_cnt, motion_min = count_rising_edges(t_ms, gb_binary, motion_intervals)
    fp_light_cnt, light_min = count_rising_edges(t_ms, gb_binary, light_intervals)

    fp_motion_per_min = float(fp_motion_cnt / motion_min) if motion_min > 1e-6 else 0.0
    fp_light_per_min = float(fp_light_cnt / light_min) if light_min > 1e-6 else 0.0

    # gate decision
    gate_cfg = config.get("gate", {})
    auc_min = float(gate_cfg.get("auc_pos_neg_min", 0.80))
    fp_m_max = float(gate_cfg.get("false_positive_motion_per_min_max", 1.0))
    fp_l_max = float(gate_cfg.get("false_positive_light_per_min_max", 1.0))

    reasons = []
    gate_pass = True
    if not (np.isfinite(auc) and auc >= auc_min):
        gate_pass = False
        reasons.append(f"auc_pos_neg < {auc_min} (got {auc})")
    if fp_motion_per_min > fp_m_max:
        gate_pass = False
        reasons.append(f"false_positive_motion_per_min > {fp_m_max} (got {fp_motion_per_min})")
    if fp_light_per_min > fp_l_max:
        gate_pass = False
        reasons.append(f"false_positive_light_per_min > {fp_l_max} (got {fp_light_per_min})")

    report = {
        "schema_version": "1.0",
        "session_id": session_id,
        "gate": {"pass": bool(gate_pass), "reasons": reasons},
        "metrics": {
            "baseline_sd": baseline_sd,
            "baseline_drift_per_min": baseline_drift_per_min,
            "auc_pos_neg": auc,
            "false_positive_rate_motion_per_min": fp_motion_per_min,
            "false_positive_rate_light_per_min": fp_light_per_min,
        },
        "threshold": {
            "value": float(threshold) if threshold is not None else None,
            "method": "mean_plus_k_sigma",
            "k": float(config.get("pilot_fft", {}).get("threshold_sigma", 3.0)),
        },
        "params": {
            "roi_size_px": int(config.get("roi", {}).get("size_px", 160)),
            "radial_band": config.get("pilot_fft", {}).get("radial_band", {}),
            "smooth_window_sec": float(config.get("pilot_fft", {}).get("smooth_window_sec", 1.0)),
        },
        "generated_at_pc_ms": int(time.time() * 1000),
    }

    (out_dir / "pilot_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save series
    import csv
    with (out_dir / "gb_index.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["pc_rx_ts_ms","gb_index","gb_smooth","gb_binary"])
        w.writeheader()
        for i in range(len(t_ms)):
            w.writerow({
                "pc_rx_ts_ms": int(t_ms[i]),
                "gb_index": float(gb[i]),
                "gb_smooth": float(gb_smooth[i]),
                "gb_binary": int(gb_binary[i]),
            })

    # Plot
    fig = plt.figure(figsize=(10, 4))
    ax = fig.add_subplot(1, 1, 1)
    # Use relative seconds for x-axis
    x = (t_ms - t_ms[0]) / 1000.0 if len(t_ms) else np.array([])
    ax.plot(x, gb_smooth, label="gb_smooth")
    if threshold is not None:
        ax.axhline(threshold, linestyle="--", label="threshold")

    def _shade(intervals, label):
        for (a, b) in intervals:
            xa = (a - t_ms[0]) / 1000.0
            xb = (b - t_ms[0]) / 1000.0
            ax.axvspan(xa, xb, alpha=0.15, label=label)

    if stim_intervals:
        _shade(stim_intervals, "stim")
    if motion_intervals:
        _shade(motion_intervals, "motion")
    if light_intervals:
        _shade(light_intervals, "light")
    if baseline_interval:
        _shade([baseline_interval], "baseline")

    ax.set_xlabel("time (s)")
    ax.set_ylabel("gb index (smooth)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "pilot_plot.png", dpi=160)
    plt.close(fig)

    return report
