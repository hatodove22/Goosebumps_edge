#!/usr/bin/env python3
"""
Simulate a device sending JPEG frames via POST /upload.
This is for testing the Collector PC without hardware.
"""
import argparse
import io
import time
import random
from pathlib import Path

import numpy as np
from PIL import Image
import requests


def make_fake_frame(w: int, h: int, t: float) -> Image.Image:
    # Simple texture pattern + moving gradient (can create FFT changes)
    yy, xx = np.indices((h, w))
    base = (np.sin(xx / 6.0 + t) + np.sin(yy / 9.0 - t * 0.8)) * 40 + 120
    noise = np.random.randn(h, w) * 6
    img = np.clip(base + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(img, mode="L").convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", type=str, default="http://127.0.0.1:8000")
    ap.add_argument("--fps", type=float, default=8.0)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--w", type=int, default=320)
    ap.add_argument("--h", type=int, default=240)
    args = ap.parse_args()

    dt = 1.0 / args.fps
    n = int(args.seconds * args.fps)
    for i in range(n):
        t = time.time()
        img = make_fake_frame(args.w, args.h, t)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        jpeg = buf.getvalue()

        files = {"image": ("frame.jpg", jpeg, "image/jpeg")}
        gx = random.uniform(0, 300)
        gy = random.uniform(0, 300)
        gz = random.uniform(0, 300)
        g_norm = (gx * gx + gy * gy + gz * gz) ** 0.5

        data = {
            "frame_id": str(i),
            "device_ts_ms": str(int((t * 1000) % 1_000_000_000)),
            "width": str(args.w),
            "height": str(args.h),
            # IMU mock (same field names as AtomS3R-M12 firmware)
            "ax": str(random.uniform(-1.0, 1.0)),
            "ay": str(random.uniform(-1.0, 1.0)),
            "az": str(random.uniform(-1.0, 1.0)),
            "gx": str(gx),
            "gy": str(gy),
            "gz": str(gz),
            "g_norm": str(g_norm),
        }
        r = requests.post(args.host.rstrip("/") + "/upload", files=files, data=data, timeout=2.0)
        if r.status_code != 200:
            print("upload failed", r.status_code, r.text)
        else:
            js = r.json()
            print("uploaded", js.get("frame_id"), "saved", js.get("saved"), "fps", js.get("fps"))
        time.sleep(dt)

if __name__ == "__main__":
    main()
