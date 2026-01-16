from __future__ import annotations

import math
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image
import io


def extract_roi_gray(jpeg_bytes: bytes, width: int, height: int, roi_size: int) -> np.ndarray:
    """
    Decode JPEG and extract fixed-center square ROI as grayscale uint8.
    """
    img = Image.open(io.BytesIO(jpeg_bytes)).convert("L")  # grayscale
    # If width/height is inconsistent, trust decoded size
    W, H = img.size
    S = int(min(roi_size, W, H))
    x0 = max(0, (W - S) // 2)
    y0 = max(0, (H - S) // 2)
    roi = img.crop((x0, y0, x0 + S, y0 + S))
    return np.array(roi, dtype=np.uint8)


def _laplacian_var(gray: np.ndarray) -> float:
    """
    Compute variance of Laplacian using a simple 3x3 kernel.
    """
    # 3x3 Laplacian kernel
    k = np.array([[0, 1, 0],
                  [1, -4, 1],
                  [0, 1, 0]], dtype=np.float32)
    g = gray.astype(np.float32)
    # convolution valid region
    # pad with edge
    gp = np.pad(g, 1, mode="edge")
    out = (
        k[0,0]*gp[0:-2,0:-2] + k[0,1]*gp[0:-2,1:-1] + k[0,2]*gp[0:-2,2:] +
        k[1,0]*gp[1:-1,0:-2] + k[1,1]*gp[1:-1,1:-1] + k[1,2]*gp[1:-1,2:] +
        k[2,0]*gp[2:,0:-2] + k[2,1]*gp[2:,1:-1] + k[2,2]*gp[2:,2:]
    )
    return float(np.var(out))


def _banding_score(gray: np.ndarray) -> float:
    """
    Very simple banding heuristic:
    - compute per-row mean signal
    - banding_score = Var(diff(row_mean))
    """
    row_mean = gray.astype(np.float32).mean(axis=1)
    d = np.diff(row_mean)
    return float(np.var(d))


def compute_quality_metrics(gray_roi: np.ndarray, config: Dict[str, Any], imu: Dict[str, Any]) -> Dict[str, Any]:
    g = gray_roi
    luma_mean = float(g.mean())
    sat_white_ratio = float(np.mean(g >= 250))
    sat_black_ratio = float(np.mean(g <= 5))
    blur = _laplacian_var(g)
    band = _banding_score(g)

    # Motion from IMU (optional)
    g_norm = None
    if "g_norm" in imu:
        try:
            g_norm = float(imu.get("g_norm"))
        except Exception:
            g_norm = None
    else:
        # compute from gx,gy,gz if present
        try:
            gx = float(imu.get("gx"))
            gy = float(imu.get("gy"))
            gz = float(imu.get("gz"))
            if all(math.isfinite(v) for v in [gx, gy, gz]):
                g_norm = float(math.sqrt(gx*gx + gy*gy + gz*gz))
        except Exception:
            g_norm = None

    blur_threshold = float(config.get("quality", {}).get("blur_threshold", 80.0))
    gnorm_threshold = float(config.get("quality", {}).get("imu_gnorm_threshold", 150.0))

    motion_flag = 0
    if blur < blur_threshold:
        motion_flag = 1
    if g_norm is not None and math.isfinite(g_norm) and g_norm > gnorm_threshold:
        motion_flag = 1

    return {
        "luma_mean": luma_mean,
        "sat_white_ratio": sat_white_ratio,
        "sat_black_ratio": sat_black_ratio,
        "blur_laplacian_var": blur,
        "banding_score": band,
        "motion_flag": motion_flag,
    }
