#!/usr/bin/env python3
"""Run LBP+LogReg inference on a recorded session.

Outputs
- <session_dir>/derived/pred_lbp_lr.csv
- <session_dir>/derived/pred_lbp_lr_report.json (if labels exist)

Usage
  python tools/infer_lbp_lr.py --model models/lbp_lr_model.json <session_dir>

Tip (uv)
  cd collector
  uv run python ../tools/infer_lbp_lr.py --model ../models/lbp_lr_model.json ../dataset/subject_001/2026-01-16_session_01
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# Optional plotting
try:
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None

# Local helper
import sys
THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from roi_utils import get_roi_size, iter_frames, load_labels_map, load_meta, load_quality_map, load_roi_gray
from train_lbp_lr import auc_mann_whitney, lbp_hist_8, sigmoid


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir", type=str)
    ap.add_argument("--model", type=str, required=True)
    ap.add_argument("--out", type=str, default="")
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--require-motion-ok", action="store_true")
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()

    sdir = Path(args.session_dir)
    model = load_json(Path(args.model))
    if model.get("type") != "lbp_lr":
        raise SystemExit(f"Unsupported model type: {model.get('type')}")

    weights = np.asarray(model["model"]["weights"], dtype=np.float32)
    bias = float(model["model"]["bias"])
    thr = float(model.get("train", {}).get("threshold", {}).get("threshold", 0.5))

    feat_cfg = model.get("feature", {}).get("roi", {})
    input_size = int(feat_cfg.get("input_size", 64))

    meta = load_meta(sdir)
    roi_size = get_roi_size(meta, default=int(feat_cfg.get("roi_size", 160)))

    frames = iter_frames(sdir)
    q_map = load_quality_map(sdir)
    lab_map = load_labels_map(sdir)

    out_csv = Path(args.out) if args.out else (sdir / "derived" / "pred_lbp_lr.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "frame_id",
        "pc_rx_ts_ms",
        "filename",
        "p_prob",
        "pred",
        "label",
        "motion_flag_logged",
    ]

    rows: List[Dict[str, Any]] = []
    y_list: List[int] = []
    p_list: List[float] = []

    for idx, fr in enumerate(frames):
        if args.stride > 1 and (idx % int(args.stride) != 0):
            continue

        q = q_map.get(fr.frame_id, {})
        if args.require_motion_ok:
            try:
                if int(str(q.get("motion_flag", "0")).strip()) == 1:
                    continue
            except Exception:
                pass

        img_path = sdir / fr.filename
        if not img_path.exists():
            continue

        gray = load_roi_gray(img_path, roi_size=roi_size, out_size=input_size)
        x = lbp_hist_8(gray)
        p = float(sigmoid(np.asarray([float(x @ weights + bias)], dtype=np.float32))[0])
        pred = 1 if p >= thr else 0

        lab = lab_map.get(fr.frame_id, {})
        y_s = str(lab.get("piloerection", "")).strip()
        y = int(y_s) if y_s in ["0", "1"] else -1

        rows.append(
            {
                "frame_id": fr.frame_id,
                "pc_rx_ts_ms": fr.pc_rx_ts_ms,
                "filename": fr.filename,
                "p_prob": p,
                "pred": pred,
                "label": y if y >= 0 else "",
                "motion_flag_logged": q.get("motion_flag", ""),
            }
        )

        if y >= 0:
            y_list.append(y)
            p_list.append(p)

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print("wrote", out_csv)

    report: Dict[str, Any] = {
        "session_dir": str(sdir),
        "model": str(args.model),
        "n_rows": int(len(rows)),
        "roi_size": int(roi_size),
        "input_size": int(input_size),
        "threshold": float(thr),
        "has_labels": bool(len(y_list) > 0),
    }

    if y_list:
        y = np.asarray(y_list, dtype=np.int32)
        p = np.asarray(p_list, dtype=np.float32)
        auc = auc_mann_whitney(y, p)
        pred = (p >= thr).astype(np.int32)
        tp = int(((pred == 1) & (y == 1)).sum())
        tn = int(((pred == 0) & (y == 0)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        report["auc"] = float(auc)
        report["confusion"] = {"tp": tp, "tn": tn, "fp": fp, "fn": fn}
        report["counts"] = {"pos": int((y == 1).sum()), "neg": int((y == 0).sum())}

    out_json = out_csv.parent / "pred_lbp_lr_report.json"
    save_json(out_json, report)
    print("wrote", out_json)

    # Optional plot
    if (not args.no_plot) and (plt is not None) and rows:
        try:
            t_ms = np.asarray([int(r["pc_rx_ts_ms"]) for r in rows], dtype=np.int64)
            t_s = (t_ms - t_ms[0]).astype(np.float64) / 1000.0
            p_all = np.asarray([float(r["p_prob"]) for r in rows], dtype=np.float32)
            fig = plt.figure(figsize=(10, 4))
            ax = fig.add_subplot(1, 1, 1)
            ax.plot(t_s, p_all)
            ax.axhline(thr, linestyle="--")
            ax.set_title("LBP+LR probability")
            ax.set_xlabel("time [s]")
            ax.set_ylabel("p(goosebumps)")
            fig.tight_layout()
            out_png = out_csv.parent / "pred_lbp_lr_plot.png"
            fig.savefig(out_png, dpi=150)
            plt.close(fig)
            print("wrote", out_png)
        except Exception as e:
            print("plot skipped:", e)


if __name__ == "__main__":
    main()
