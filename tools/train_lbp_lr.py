#!/usr/bin/env python3
"""Train a lightweight edge-friendly model: LBP histogram + Logistic Regression.

Why LBP + LR
- Runs fast on microcontrollers (only integer comparisons + histogram + dot product).
- More robust than a single scalar threshold in many lighting conditions.
- Training can be done with numpy only (no scikit-learn dependency).

High-level pipeline
1) Collect sessions with labels (events goose_on/off) and run tools/make_labels.py
2) Run this script on dataset_root to train a model (JSON)
3) Export to a C header via tools/export_lbp_lr_header.py
4) (Optional) Validate on held-out sessions via tools/infer_lbp_lr.py

Usage
  python tools/train_lbp_lr.py --dataset-root dataset --out models/lbp_lr_model.json

Tip (uv)
  cd collector
  uv run python ../tools/train_lbp_lr.py --dataset-root ../dataset --out ../models/lbp_lr_model.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# Local helper (works even when tools/ is not a package)
import sys
THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from roi_utils import get_roi_size, load_meta, load_quality_map, load_roi_gray


def sigmoid(z: np.ndarray) -> np.ndarray:
    zc = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-zc))


def auc_mann_whitney(y_true: np.ndarray, scores: np.ndarray) -> float:
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


def lbp_hist_8(gray: np.ndarray) -> np.ndarray:
    """Compute 8-neighbor LBP histogram (256 bins).

    Input gray must be uint8, 2D.
    """
    if gray.ndim != 2:
        raise ValueError("gray must be 2D")
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        raise ValueError("gray too small")

    c = gray[1:-1, 1:-1]
    code = np.zeros_like(c, dtype=np.uint8)

    # Clockwise, starting from top-left (bit7) to left (bit0)
    code |= ((gray[0:-2, 0:-2] >= c).astype(np.uint8) << 7)
    code |= ((gray[0:-2, 1:-1] >= c).astype(np.uint8) << 6)
    code |= ((gray[0:-2, 2:  ] >= c).astype(np.uint8) << 5)
    code |= ((gray[1:-1, 2:  ] >= c).astype(np.uint8) << 4)
    code |= ((gray[2:  , 2:  ] >= c).astype(np.uint8) << 3)
    code |= ((gray[2:  , 1:-1] >= c).astype(np.uint8) << 2)
    code |= ((gray[2:  , 0:-2] >= c).astype(np.uint8) << 1)
    code |= ((gray[1:-1, 0:-2] >= c).astype(np.uint8) << 0)

    hist = np.bincount(code.ravel(), minlength=256).astype(np.float32)
    s = float(hist.sum())
    if s > 0:
        hist /= s
    return hist


def load_labels_rows(labels_csv: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with labels_csv.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            out.append(dict(row))
    return out


def find_session_dirs(dataset_root: Path) -> List[Path]:
    # Prefer labels.csv because supervised training requires labels.
    # Structure: dataset/subject_XXX/<session>/labels.csv
    out = []
    for p in dataset_root.rglob("labels.csv"):
        sdir = p.parent
        if (sdir / "frames.csv").exists() and (sdir / "frames").exists():
            out.append(sdir)
    out.sort()
    return out


def split_sessions(session_dirs: List[Path], holdout_ratio: float, seed: int) -> Tuple[List[Path], List[Path]]:
    rnd = random.Random(seed)
    s = list(session_dirs)
    rnd.shuffle(s)
    n_val = int(round(len(s) * holdout_ratio))
    n_val = max(1, n_val) if len(s) >= 2 else 0
    val = s[:n_val]
    train = s[n_val:]
    return train, val


def select_samples_from_session(
    session_dir: Path,
    roi_size_default: int,
    input_size: int,
    stride: int,
    max_per_class: int,
    require_motion_ok: bool,
    seed: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return X (N,D) and y (N,) for one session."""

    meta = load_meta(session_dir)
    roi_size = get_roi_size(meta, default=roi_size_default)
    q_map = load_quality_map(session_dir)

    labels_csv = session_dir / "labels.csv"
    rows = load_labels_rows(labels_csv)

    # Collect eligible frame paths for pos/neg
    pos: List[Path] = []
    neg: List[Path] = []

    for idx, r in enumerate(rows):
        if stride > 1 and (idx % stride != 0):
            continue
        try:
            if str(r.get("use_flag", "1")).strip() not in ["1", ""]:
                continue
            y = int(str(r.get("piloerection", "0")).strip())
            fid = int(str(r.get("frame_id", "-1")).strip())
            filename = str(r.get("filename", "")).strip()
        except Exception:
            continue

        if not filename:
            continue
        img_path = session_dir / filename
        if not img_path.exists():
            continue

        if require_motion_ok:
            q = q_map.get(fid)
            if q is not None:
                try:
                    if int(str(q.get("motion_flag", "0")).strip()) == 1:
                        continue
                except Exception:
                    pass

        if y == 1:
            pos.append(img_path)
        else:
            neg.append(img_path)

    rnd = random.Random(seed)
    rnd.shuffle(pos)
    rnd.shuffle(neg)

    if max_per_class > 0:
        pos = pos[:max_per_class]
        neg = neg[:max_per_class]

    xs: List[np.ndarray] = []
    ys: List[int] = []

    for y, paths in [(1, pos), (0, neg)]:
        for p in paths:
            try:
                gray = load_roi_gray(p, roi_size=roi_size, out_size=input_size)
                feat = lbp_hist_8(gray)
                xs.append(feat)
                ys.append(y)
            except Exception:
                continue

    if not xs:
        return np.zeros((0, 256), dtype=np.float32), np.zeros((0,), dtype=np.int32)

    X = np.stack(xs, axis=0).astype(np.float32)
    y_arr = np.asarray(ys, dtype=np.int32)
    return X, y_arr


def train_logreg(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    lr: float,
    epochs: int,
    batch_size: int,
    l2: float,
    seed: int,
) -> Tuple[np.ndarray, float, Dict[str, Any]]:
    """Train logistic regression with minibatch SGD."""
    rnd = np.random.default_rng(seed)

    N, D = X_train.shape
    w = rnd.normal(loc=0.0, scale=0.01, size=(D,)).astype(np.float32)
    b = 0.0

    # Class weights (balance)
    n_pos = float((y_train == 1).sum())
    n_neg = float((y_train == 0).sum())
    w_pos = (N / (2.0 * n_pos)) if n_pos > 0 else 1.0
    w_neg = (N / (2.0 * n_neg)) if n_neg > 0 else 1.0

    def loss_and_metrics(X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        z = X @ w + b
        p = sigmoid(z)
        eps = 1e-7
        # weighted BCE
        sw = np.where(y == 1, w_pos, w_neg).astype(np.float32)
        bce = -np.mean(sw * (y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)))
        reg = 0.5 * l2 * float(np.sum(w * w))
        auc = auc_mann_whitney(y, p)
        return {"loss": float(bce + reg), "bce": float(bce), "reg": float(reg), "auc": float(auc)}

    history: List[Dict[str, Any]] = []

    idx_all = np.arange(N, dtype=np.int32)
    for ep in range(1, int(epochs) + 1):
        rnd.shuffle(idx_all)
        for start in range(0, N, int(batch_size)):
            batch_idx = idx_all[start : start + int(batch_size)]
            Xb = X_train[batch_idx]
            yb = y_train[batch_idx].astype(np.float32)

            z = Xb @ w + b
            p = sigmoid(z)

            # weights per sample
            sw = np.where(yb == 1.0, w_pos, w_neg).astype(np.float32)

            # gradient of weighted BCE
            err = (p - yb) * sw
            grad_w = (Xb.T @ err) / float(len(batch_idx)) + l2 * w
            grad_b = float(np.mean(err))

            w -= float(lr) * grad_w.astype(np.float32)
            b -= float(lr) * grad_b

        tr = loss_and_metrics(X_train, y_train)
        va = loss_and_metrics(X_val, y_val) if X_val.size else {"loss": float("nan"), "auc": float("nan")}
        row = {"epoch": ep, "train": tr, "val": va}
        history.append(row)
        if ep == 1 or ep % 5 == 0 or ep == epochs:
            print(f"epoch {ep:03d}: train loss={tr['loss']:.4f} auc={tr['auc']:.3f} | val loss={va['loss']:.4f} auc={va['auc']:.3f}")

    metrics = {"history": history, "class_weights": {"pos": float(w_pos), "neg": float(w_neg)}}
    return w, float(b), metrics


def find_best_threshold(y: np.ndarray, p: np.ndarray) -> Dict[str, Any]:
    """Pick threshold that maximizes balanced accuracy on validation."""
    if y.size == 0:
        return {"threshold": 0.5}
    best = {"threshold": 0.5, "balanced_acc": -1.0}
    for thr in np.linspace(0.05, 0.95, 19):
        pred = (p >= thr).astype(np.int32)
        tp = int(((pred == 1) & (y == 1)).sum())
        tn = int(((pred == 0) & (y == 0)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        tpr = tp / max(1, (tp + fn))
        tnr = tn / max(1, (tn + fp))
        bacc = 0.5 * (tpr + tnr)
        if bacc > best["balanced_acc"]:
            best = {
                "threshold": float(thr),
                "balanced_acc": float(bacc),
                "tpr": float(tpr),
                "tnr": float(tnr),
                "tp": tp,
                "tn": tn,
                "fp": fp,
                "fn": fn,
            }
    return best


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-root", type=str, required=True)
    ap.add_argument("--out", type=str, default="models/lbp_lr_model.json")
    ap.add_argument("--roi-size", type=int, default=160, help="fallback ROI size (used if meta.json missing)")
    ap.add_argument("--input-size", type=int, default=64, help="ROI is resized to input_size x input_size")
    ap.add_argument("--stride", type=int, default=3, help="subsample labels rows (reduces temporal correlation)")
    ap.add_argument("--max-per-class", type=int, default=400, help="cap samples per class per session (0: no cap)")
    ap.add_argument("--require-motion-ok", action="store_true", help="drop frames with motion_flag=1")
    ap.add_argument("--holdout", type=float, default=0.2, help="fraction of sessions used for validation")
    ap.add_argument("--seed", type=int, default=42)

    ap.add_argument("--lr", type=float, default=0.5)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--l2", type=float, default=1e-3)
    args = ap.parse_args()

    dataset_root = Path(args.dataset_root)
    if not dataset_root.exists():
        raise SystemExit(f"dataset_root not found: {dataset_root}")

    session_dirs = find_session_dirs(dataset_root)
    if not session_dirs:
        raise SystemExit(
            "No labeled sessions found. Ensure labels.csv exists. "
            "Run: python tools/make_labels.py <session_dir>"
        )

    train_dirs, val_dirs = split_sessions(session_dirs, holdout_ratio=float(args.holdout), seed=int(args.seed))
    print("sessions:", len(session_dirs), "train:", len(train_dirs), "val:", len(val_dirs))

    # Build dataset
    X_tr_list: List[np.ndarray] = []
    y_tr_list: List[np.ndarray] = []
    for sdir in train_dirs:
        Xs, ys = select_samples_from_session(
            session_dir=sdir,
            roi_size_default=int(args.roi_size),
            input_size=int(args.input_size),
            stride=int(args.stride),
            max_per_class=int(args.max_per_class),
            require_motion_ok=bool(args.require_motion_ok),
            seed=int(args.seed),
        )
        if Xs.shape[0] > 0:
            X_tr_list.append(Xs)
            y_tr_list.append(ys)

    X_va_list: List[np.ndarray] = []
    y_va_list: List[np.ndarray] = []
    for sdir in val_dirs:
        Xs, ys = select_samples_from_session(
            session_dir=sdir,
            roi_size_default=int(args.roi_size),
            input_size=int(args.input_size),
            stride=int(args.stride),
            max_per_class=int(args.max_per_class),
            require_motion_ok=bool(args.require_motion_ok),
            seed=int(args.seed) + 999,
        )
        if Xs.shape[0] > 0:
            X_va_list.append(Xs)
            y_va_list.append(ys)

    if not X_tr_list:
        raise SystemExit("No training samples. Check labels/use_flag/motion filter.")

    X_train = np.concatenate(X_tr_list, axis=0).astype(np.float32)
    y_train = np.concatenate(y_tr_list, axis=0).astype(np.int32)

    X_val = np.concatenate(X_va_list, axis=0).astype(np.float32) if X_va_list else np.zeros((0, 256), dtype=np.float32)
    y_val = np.concatenate(y_va_list, axis=0).astype(np.int32) if y_va_list else np.zeros((0,), dtype=np.int32)

    print("train samples:", X_train.shape, "pos:", int((y_train == 1).sum()), "neg:", int((y_train == 0).sum()))
    print("val   samples:", X_val.shape, "pos:", int((y_val == 1).sum()), "neg:", int((y_val == 0).sum()))

    w, b, metrics = train_logreg(
        X_train,
        y_train,
        X_val,
        y_val,
        lr=float(args.lr),
        epochs=int(args.epochs),
        batch_size=int(args.batch_size),
        l2=float(args.l2),
        seed=int(args.seed),
    )

    # Choose threshold (validation)
    thr_info = {"threshold": 0.5}
    val_auc = float("nan")
    if X_val.shape[0] > 0:
        p_val = sigmoid(X_val @ w + b)
        val_auc = auc_mann_whitney(y_val, p_val)
        thr_info = find_best_threshold(y_val, p_val)

    model = {
        "type": "lbp_lr",
        "created_at": int(time.time()),
        "feature": {
            "lbp": {"neighbors": 8, "radius": 1, "bins": 256},
            "roi": {"roi_size": int(args.roi_size), "input_size": int(args.input_size)},
        },
        "train": {
            "dataset_root": str(dataset_root),
            "sessions_total": int(len(session_dirs)),
            "sessions_train": [str(p) for p in train_dirs],
            "sessions_val": [str(p) for p in val_dirs],
            "params": {
                "lr": float(args.lr),
                "epochs": int(args.epochs),
                "batch_size": int(args.batch_size),
                "l2": float(args.l2),
                "stride": int(args.stride),
                "max_per_class": int(args.max_per_class),
                "require_motion_ok": bool(args.require_motion_ok),
                "seed": int(args.seed),
            },
            "val_auc": float(val_auc),
            "threshold": thr_info,
            "metrics": metrics,
        },
        "model": {
            "weights": w.astype(np.float32).tolist(),
            "bias": float(b),
        },
    }

    out_path = Path(args.out)
    save_json(out_path, model)
    print("wrote", out_path)


if __name__ == "__main__":
    main()
