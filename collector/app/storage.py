from __future__ import annotations

import csv
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

DATASET_SCHEMA_VERSION = "1.0"


class CsvAppender:
    def __init__(self, path: Path, fieldnames: list[str]):
        self.path = path
        self.fieldnames = fieldnames
        self._lock = threading.Lock()
        self._fp = None
        self._writer = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self.path.exists()
        self._fp = self.path.open("a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fp, fieldnames=self.fieldnames)
        if is_new:
            self._writer.writeheader()
            self._fp.flush()

    def append(self, row: Dict[str, Any]) -> None:
        if self._fp is None or self._writer is None:
            raise RuntimeError(f"CSV not opened: {self.path}")
        with self._lock:
            self._writer.writerow(row)
            self._fp.flush()

    def close(self) -> None:
        if self._fp:
            self._fp.close()
        self._fp = None
        self._writer = None


@dataclass
class SessionStorage:
    dataset_root: Path
    subject_id: str
    session_id: str

    base_dir: Optional[Path] = None
    frames_dir: Optional[Path] = None
    pilot_dir: Optional[Path] = None

    frames_csv: Optional[CsvAppender] = None
    imu_csv: Optional[CsvAppender] = None
    events_csv: Optional[CsvAppender] = None
    quality_csv: Optional[CsvAppender] = None

    _saved_frame_ids: set[int] = None

    def open(self) -> None:
        self.base_dir = self.dataset_root / f"subject_{self.subject_id}" / self.session_id
        self.frames_dir = self.base_dir / "frames"
        self.pilot_dir = self.base_dir / "pilot"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.pilot_dir.mkdir(parents=True, exist_ok=True)

        self._saved_frame_ids = set()

        # Create meta.json placeholder if not exists (caller should update later if needed)
        meta_path = self.base_dir / "meta.json"
        if not meta_path.exists():
            meta = {
                "schema_version": DATASET_SCHEMA_VERSION,
                "subject_id": self.subject_id,
                "session_id": self.session_id,
                "created_at_pc_ms": int(time.time() * 1000),
                "notes": "",
                "software": {"collector_version": "dev"},
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        self.frames_csv = CsvAppender(self.base_dir / "frames.csv", fieldnames=[
            "frame_id","device_ts_ms","pc_rx_ts_ms","filename","width","height","jpeg_bytes","drop_flag"
        ])
        self.imu_csv = CsvAppender(self.base_dir / "imu.csv", fieldnames=[
            "pc_rx_ts_ms","frame_id","ax","ay","az","gx","gy","gz","g_norm"
        ])
        self.events_csv = CsvAppender(self.base_dir / "events.csv", fieldnames=[
            "pc_ts_ms","type","value","note"
        ])
        self.quality_csv = CsvAppender(self.base_dir / "quality.csv", fieldnames=[
            "frame_id","pc_rx_ts_ms","luma_mean","sat_white_ratio","sat_black_ratio","blur_laplacian_var","banding_score","motion_flag"
        ])

        for c in [self.frames_csv, self.imu_csv, self.events_csv, self.quality_csv]:
            c.open()

    def close(self) -> None:
        for c in [self.frames_csv, self.imu_csv, self.events_csv, self.quality_csv]:
            if c:
                c.close()

    def update_meta(self, meta: Dict[str, Any]) -> None:
        if not self.base_dir:
            raise RuntimeError("Storage not opened")
        meta_path = self.base_dir / "meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def log_event(self, event_type: str, value: Any, note: str = "") -> None:
        if not self.events_csv:
            return
        self.events_csv.append({
            "pc_ts_ms": int(time.time() * 1000),
            "type": event_type,
            "value": value,
            "note": note or "",
        })

    def save_frame_and_logs(
        self,
        frame_id: int,
        device_ts_ms: int,
        pc_rx_ts_ms: int,
        width: int,
        height: int,
        jpeg: bytes,
        extra: Dict[str, Any],
        quality: Dict[str, Any],
    ) -> bool:
        if not self.base_dir or not self.frames_dir or not self.frames_csv or not self.quality_csv:
            return False

        # de-dup based on frame_id
        drop_flag = 0
        filename = f"frames/{frame_id:06d}.jpg"
        out_path = self.base_dir / filename

        if frame_id in self._saved_frame_ids or out_path.exists():
            # likely retransmission
            drop_flag = 1
        else:
            out_path.write_bytes(jpeg)
            self._saved_frame_ids.add(frame_id)

        self.frames_csv.append({
            "frame_id": frame_id,
            "device_ts_ms": device_ts_ms,
            "pc_rx_ts_ms": pc_rx_ts_ms,
            "filename": filename if drop_flag == 0 else "",
            "width": width,
            "height": height,
            "jpeg_bytes": len(jpeg),
            "drop_flag": drop_flag,
        })

        # IMU (optional)
        if self.imu_csv:
            ax = float(extra.get("ax", "nan")) if "ax" in extra else float("nan")
            ay = float(extra.get("ay", "nan")) if "ay" in extra else float("nan")
            az = float(extra.get("az", "nan")) if "az" in extra else float("nan")
            gx = float(extra.get("gx", "nan")) if "gx" in extra else float("nan")
            gy = float(extra.get("gy", "nan")) if "gy" in extra else float("nan")
            gz = float(extra.get("gz", "nan")) if "gz" in extra else float("nan")
            g_norm = float(extra.get("g_norm", "nan")) if "g_norm" in extra else float("nan")
            self.imu_csv.append({
                "pc_rx_ts_ms": pc_rx_ts_ms,
                "frame_id": frame_id,
                "ax": ax, "ay": ay, "az": az,
                "gx": gx, "gy": gy, "gz": gz,
                "g_norm": g_norm,
            })

        self.quality_csv.append({
            "frame_id": frame_id,
            "pc_rx_ts_ms": pc_rx_ts_ms,
            "luma_mean": float(quality.get("luma_mean", float("nan"))),
            "sat_white_ratio": float(quality.get("sat_white_ratio", float("nan"))),
            "sat_black_ratio": float(quality.get("sat_black_ratio", float("nan"))),
            "blur_laplacian_var": float(quality.get("blur_laplacian_var", float("nan"))),
            "banding_score": float(quality.get("banding_score", float("nan"))),
            "motion_flag": int(quality.get("motion_flag", 0)),
        })
        return drop_flag == 0
