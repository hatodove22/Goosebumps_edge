from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple
from collections import deque

import numpy as np

from .storage import SessionStorage
from .metrics import compute_quality_metrics, extract_roi_gray
from .pilot_fft import gb_index_from_roi, smooth_series
from .device_udp import send_udp_json_oneway


@dataclass
class BaselineStats:
    mean: float
    std: float
    threshold_k: float
    threshold_value: float
    computed_at_pc_ms: int


@dataclass
class LatestFrame:
    jpeg: bytes
    frame_id: int
    device_ts_ms: int
    pc_rx_ts_ms: int
    width: int
    height: int


@dataclass
class SessionState:
    active: bool = False
    subject_id: Optional[str] = None
    session_id: Optional[str] = None
    operator: Optional[str] = None
    body_site: str = "forearm"
    notes: str = ""
    dataset_root: Path = Path("dataset")

    storage: Optional[SessionStorage] = None

    # Runtime info
    last_device_ip: Optional[str] = None
    latest_frame: Optional[LatestFrame] = None
    last_fps: float = 0.0
    _rx_times: Deque[float] = field(default_factory=lambda: deque(maxlen=60))

    # Latest sensor/quality snapshots (for UI)
    last_imu: Dict[str, Any] = field(default_factory=dict)
    last_quality: Dict[str, Any] = field(default_factory=dict)
    last_gb_index: float = 0.0

    # Computed series (in-memory; for long sessions can be moved to file)
    series_lock: threading.Lock = field(default_factory=threading.Lock)
    gb_series: List[Tuple[int, int, float]] = field(default_factory=list)  # (frame_id, pc_rx_ts_ms, gb_index)
    quality_series: List[Dict[str, Any]] = field(default_factory=list)

    baseline: Optional[BaselineStats] = None
    auto_luma_enabled: bool = False
    auto_luma_integral: float = 0.0
    current_led_pwm: int = 0
    _last_auto_led_ms: int = 0
    _last_auto_led_pwm: int = -1

    # Config
    config: Dict[str, Any] = field(default_factory=dict)

    def update_fps(self) -> None:
        now = time.time()
        self._rx_times.append(now)
        if len(self._rx_times) >= 2:
            dt = self._rx_times[-1] - self._rx_times[0]
            if dt > 0:
                self.last_fps = (len(self._rx_times) - 1) / dt

    def ensure_dataset_root(self) -> None:
        self.dataset_root.mkdir(parents=True, exist_ok=True)

    def start_session(self, subject_id: str, session_id: str, operator: str = "", body_site: str = "forearm", notes: str = "") -> None:
        if self.active:
            raise RuntimeError("Session already active")
        self.ensure_dataset_root()
        self.subject_id = subject_id
        self.session_id = session_id
        self.operator = operator
        self.body_site = body_site
        self.notes = notes

        self.storage = SessionStorage(self.dataset_root, subject_id, session_id)
        self.storage.open()
        self.active = True

        # reset runtime series
        with self.series_lock:
            self.gb_series.clear()
            self.quality_series.clear()

        self.baseline = None
        self.auto_luma_integral = 0.0

        # default LED pwm from config
        self.current_led_pwm = int(self.config.get("lighting", {}).get("pwm_default", 0))
        self.storage.log_event("session_start", 1, note="")

    def stop_session(self) -> None:
        if not self.active or not self.storage:
            return
        self.storage.log_event("session_stop", 1, note="")
        self.storage.close()
        self.storage = None
        self.active = False

    def handle_upload(
        self,
        image_jpeg: bytes,
        frame_id: int,
        device_ts_ms: int,
        width: int,
        height: int,
        extra: Dict[str, Any],
        pc_rx_ts_ms: int,
        device_ip: Optional[str],
    ) -> Dict[str, Any]:
        # Update device ip if known
        if device_ip:
            self.last_device_ip = device_ip

        self.latest_frame = LatestFrame(
            jpeg=image_jpeg,
            frame_id=frame_id,
            device_ts_ms=device_ts_ms,
            pc_rx_ts_ms=pc_rx_ts_ms,
            width=width,
            height=height,
        )
        self.update_fps()

        # Compute ROI and metrics (always, even when not saving)
        roi_size = int(self.config.get("roi", {}).get("size_px", 160))
        gray_roi = extract_roi_gray(image_jpeg, width, height, roi_size)

        q = compute_quality_metrics(
            gray_roi=gray_roi,
            config=self.config,
            imu=extra,
        )

        # FFT index
        band = self.config.get("pilot_fft", {}).get("radial_band", {})
        r_min = int(band.get("r_min", 8))
        r_max = int(band.get("r_max", 28))
        gb = gb_index_from_roi(gray_roi, r_min=r_min, r_max=r_max)

        # Keep latest snapshots for the UI (best-effort)
        self.last_imu = dict(extra)
        # If device includes current LED PWM, keep local state in sync
        try:
            if "led_pwm" in extra and extra.get("led_pwm") is not None:
                self.current_led_pwm = int(extra.get("led_pwm"))
        except Exception:
            pass
        self.last_quality = dict(q)
        self.last_gb_index = float(gb)

        # Auto brightness control (optional): adjusts LED PWM via UDP
        try:
            self.maybe_auto_luma_adjust(luma_mean=float(q.get("luma_mean", 0.0)), pc_rx_ts_ms=pc_rx_ts_ms)
        except Exception:
            pass

        with self.series_lock:
            self.gb_series.append((frame_id, pc_rx_ts_ms, gb))
            q_row = dict(q)
            q_row.update({"frame_id": frame_id, "pc_rx_ts_ms": pc_rx_ts_ms})
            self.quality_series.append(q_row)

        # Save if session active
        saved = False
        if self.active and self.storage:
            saved = self.storage.save_frame_and_logs(
                frame_id=frame_id,
                device_ts_ms=device_ts_ms,
                pc_rx_ts_ms=pc_rx_ts_ms,
                width=width,
                height=height,
                jpeg=image_jpeg,
                extra=extra,
                quality=q,
            )
        return {
            "ok": True,
            "saved": bool(saved),
            "frame_id": frame_id,
            "pc_rx_ts_ms": pc_rx_ts_ms,
            "fps": self.last_fps,
            "device_ip": self.last_device_ip,
        }


    def _clamp(self, x: float, lo: float, hi: float) -> float:
        return lo if x < lo else hi if x > hi else x

    def maybe_auto_luma_adjust(self, luma_mean: float, pc_rx_ts_ms: int) -> None:
        """Auto-adjust external LED PWM to keep ROI luma near target.

        This sends UDP JSON commands to the device (fire-and-forget) at a limited rate.
        """
        if not self.auto_luma_enabled:
            return
        ip = self.last_device_ip
        if not ip:
            return

        lighting = self.config.get("lighting", {}) or {}
        pwm_min = float(lighting.get("pwm_min", 0))
        pwm_max = float(lighting.get("pwm_max", 255))
        target = float(lighting.get("auto_luma_target", 110))
        kp = float(lighting.get("auto_kp", 0.8))
        ki = float(lighting.get("auto_ki", 0.05))

        # rate limit (ms)
        min_interval_ms = 200
        if pc_rx_ts_ms - self._last_auto_led_ms < min_interval_ms:
            return
        self._last_auto_led_ms = pc_rx_ts_ms

        # PI control
        e = target - float(luma_mean)
        # integral anti-windup
        self.auto_luma_integral = self._clamp(self.auto_luma_integral + e, -1000.0, 1000.0)

        pwm_float = float(self.current_led_pwm) + kp * e + ki * self.auto_luma_integral
        pwm_new = int(round(self._clamp(pwm_float, pwm_min, pwm_max)))

        # avoid spamming tiny changes
        if pwm_new == int(self.current_led_pwm):
            return
        if abs(pwm_new - int(self.current_led_pwm)) < 1:
            return

        port = int(self.config.get("network", {}).get("device_udp_cmd_port", 3333))
        ok = send_udp_json_oneway(ip, port, {"cmd": "set_led", "pwm": int(pwm_new)})
        if ok:
            self.current_led_pwm = int(pwm_new)
            self._last_auto_led_pwm = int(pwm_new)
            if self.active and self.storage:
                # log at most at the rate limit, and only if actually changed
                self.storage.log_event("led_pwm", int(pwm_new), note="auto_luma")
    def calibrate_baseline(self, seconds: float = 10.0, k_sigma: float = 3.0) -> BaselineStats:
        """
        Use the last `seconds` of gb_index as baseline and compute threshold.
        """
        if not self.gb_series:
            raise RuntimeError("No frames received yet")

        now_ms = int(time.time() * 1000)
        start_ms = now_ms - int(seconds * 1000)

        with self.series_lock:
            xs = [gb for (_, t, gb) in self.gb_series if t >= start_ms]

        if len(xs) < 10:
            raise RuntimeError("Not enough frames in calibration window")

        mean = float(np.mean(xs))
        std = float(np.std(xs, ddof=0))
        thr = mean + k_sigma * std
        self.baseline = BaselineStats(mean=mean, std=std, threshold_k=k_sigma, threshold_value=thr, computed_at_pc_ms=now_ms)

        if self.active and self.storage:
            # Log calibration interval aligned to the window used for stats
            if self.storage.events_csv:
                self.storage.events_csv.append({
                    "pc_ts_ms": start_ms,
                    "type": "calib_start",
                    "value": 1,
                    "note": f"window_sec={seconds}",
                })
                self.storage.events_csv.append({
                    "pc_ts_ms": now_ms,
                    "type": "calib_done",
                    "value": 1,
                    "note": f"mean={mean:.6f},std={std:.6f},thr={thr:.6f},k={k_sigma}",
                })
        return self.baseline

    def compute_smoothed_and_binary(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Optional[float]]:
        """
        Returns: t_ms, gb_smooth, gb_binary, threshold
        """
        with self.series_lock:
            series = list(self.gb_series)

        if not series:
            return np.array([]), np.array([]), np.array([]), None

        frame_ids = np.array([s[0] for s in series], dtype=np.int64)
        t_ms = np.array([s[1] for s in series], dtype=np.int64)
        gb = np.array([s[2] for s in series], dtype=np.float32)

        smooth_window_sec = float(self.config.get("pilot_fft", {}).get("smooth_window_sec", 1.0))
        # approximate by sample count using current fps (fallback 12)
        fps = self.last_fps if self.last_fps > 1e-3 else float(self.config.get("camera", {}).get("target_fps", 12))
        win = max(1, int(round(smooth_window_sec * fps)))
        gb_smooth = smooth_series(gb, window=win)

        thr = self.baseline.threshold_value if self.baseline else None
        if thr is None:
            gb_binary = np.zeros_like(gb_smooth, dtype=np.int32)
        else:
            gb_binary = (gb_smooth > thr).astype(np.int32)
        return t_ms, gb_smooth, gb_binary, thr