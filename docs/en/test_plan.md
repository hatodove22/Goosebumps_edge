# Test Plan (Hardware Verification Checklist) v1.0

Updated: 2026-01-16

This document organizes the **hardware test items** for the goosebumps detection project using AtomS3R-M12 (OV3660 + BMI270) and the Collector PC (FastAPI UI), so the operator can verify everything without missing steps.

## 1. Preconditions
- The Collector PC is running and the UI is accessible.
- The Atom device can join the same LAN (Wi-Fi).
- External LED can be PWM controlled (with current limiting and heat dissipation as needed).

## 2. Connection and Basic Behavior (Highest Priority)
### 2.1 Wi-Fi Connection
- [ ] Device IP shows in Serial after boot.
- [ ] RSSI is sufficient (target: better than -70 dBm).
- [ ] No disconnect after 1 minute idle.

### 2.2 Frame Upload
- [ ] Preview updates in Collector UI (`/latest.jpg`).
- [ ] After `/session/start`, data is saved (frames/ and frames.csv).
- [ ] Saving continues for 5 minutes with no extreme dropouts.

### 2.3 Sequence and Timestamps
- [ ] frame_id increases monotonically (drop_flag=1 allowed on retransmit).
- [ ] device_ts_ms increases.
- [ ] pc_rx_ts_ms increases.

## 3. LED Control (Manual)
- [ ] PWM slider and `Send to device` change illumination.
- [ ] `led_pwm` is recorded in events.csv (manual control log).
- [ ] sat_white_ratio / sat_black_ratio respond to extreme bright/dark settings.

## 4. Auto Luma (Automatic Brightness Control)
- [ ] Turning ON `Auto Luma` follows target brightness automatically.
- [ ] While active, events.csv records `led_pwm` with note=auto_luma.
- [ ] Banding does not become severe (if it does, revisit PWM frequency and exposure).

## 5. IMU (BMI270)
- [ ] UI shows `g_norm` and `gx/gy/gz`, `ax/ay/az`.
- [ ] g_norm increases when the arm moves.
- [ ] motion_flag rises appropriately (thresholds configurable).

## 6. Quality Metrics
- [ ] luma_mean tracks brightness changes.
- [ ] blur_laplacian_var responds to focus/blur changes.
- [ ] banding_score responds to banding (even coarse detection is OK).

## 7. Pilot (FFT Gate)
### 7.1 Calibrate
- [ ] Calibrate (10 sec) shows baseline (mean/std/thr).
- [ ] events.csv records calib_start/calb_done (window aligned).

### 7.2 Positive/Negative/Confound
- [ ] stim_on/off can be recorded.
- [ ] goose_on/off can be recorded (use reaction delay if needed).
- [ ] confound_motion/light intervals can be recorded.

### 7.3 Report
- [ ] pilot_report.json / pilot_plot.png / gb_index.csv are generated.
- [ ] gate.pass matches expectation (if fail, improve observability).

## 8. Stress and Fault Tolerance
- [ ] Wi-Fi reconnects after temporary loss (firmware reconnect).
- [ ] Collector stop/restart recovers on the next session.
- [ ] Long run (30 minutes) does not crash due to memory/heat.

## 9. Data Validation (Tools)
- [ ] `python tools/validate_session.py <session_dir>` passes.
- [ ] `python tools/make_labels.py <session_dir>` generates labels.csv.
