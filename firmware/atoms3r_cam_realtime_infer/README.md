# AtomS3R-CAM Real-Time Edge Inference (LBP + Logistic Regression)

This firmware performs **on-device goosebumps inference** on the **M5Stack AtomS3R-CAM (GC0308)**:

- Capture RGB565 frames
- Crop a fixed center ROI
- Downsample to **64x64** grayscale
- Compute LBP histogram (256 bins)
- Logistic Regression probability + EMA smoothing + hysteresis
- Optional: upload frames to Collector (`/upload`) and/or post state-change events to (`/event`)

## 0) Prepare your model header

The firmware expects `include/model_lbp_lr.h`.

Generate it from the repo tools:

```bash
# from repo root (or via `collector/uv run ...`)
python tools/train_lbp_lr.py --dataset-root ./dataset --out ./models/lbp_lr_model.json
python tools/export_lbp_lr_header.py --model ./models/lbp_lr_model.json \
    --out ./firmware/atoms3r_cam_realtime_infer/include/model_lbp_lr.h
```

Then rebuild and flash.

> This project includes a placeholder header with all-zero weights, so inference will be meaningless until you replace it.

## 1) Configure Wi-Fi and Collector

Edit `include/user_config.h`:

- `WIFI_SSID` / `WIFI_PASS`
- `COLLECTOR_HOST` / `COLLECTOR_PORT`
- Optional flags:
  - `ENABLE_FRAME_UPLOAD` (true/false)
  - `ENABLE_EVENT_POST` (true/false)

## 2) Build and flash (PlatformIO)

From this folder:

```bash
pio run -t upload
pio device monitor -b 115200
```

## 3) UDP commands

The firmware listens on `UDP_CMD_PORT` (default: 3333).

Examples (JSON):

- `{"cmd":"ping"}`
- `{"cmd":"set_led","pwm":120}`
- `{"cmd":"start_upload"}` / `{"cmd":"stop_upload"}`
- `{"cmd":"calib_start"}` then after >=5 seconds `{"cmd":"calib_done"}`
- `{"cmd":"set_param","target_fps":12,"jpeg_quality":20,"thr_on":0.65,"thr_off":0.50}`

## Notes

- AtomS3R-CAM requires **GPIO18 LOW** before `esp_camera_init()` to enable camera power.
- GC0308 does **not** output JPEG natively; frame upload encodes RGB565 to JPEG in software (CPU heavy).
  If you only need on-device inference, set `ENABLE_FRAME_UPLOAD=false`.
