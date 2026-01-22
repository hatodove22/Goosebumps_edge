# Goosebumps (Piloerection) Edge AI System - Implementation Spec v1.4

Updated: 2026-01-16

## Addendum: AtomS3R-CAM (GC0308) camera power pin handling

AtomS3R-CAM uses **POWER_N on GPIO18** for the camera module. M5Stack documentation states that **GPIO18 must be set LOW before camera initialization to enable power**.

Important implementation note:
- `esp_camera` treats `pin_pwdn` as an **active-high power-down** control.
- On AtomS3R-CAM, GPIO18 is **active-low enable (POWER_N)**, so passing GPIO18 as `pin_pwdn` may cause `esp_camera` to drive it HIGH and disable the camera.

Therefore, for AtomS3R-CAM (non-M12):
- Drive **GPIO18 LOW manually** before calling esp_camera_init()
- Set camera_config.pin_pwdn = -1 to prevent esp_camera from toggling GPIO18
- GC0308 does **not** output native JPEG. Capture RGB565 and encode JPEG in software (lower FPS, higher CPU).
- Use xclk_freq_hz = 20000000 (20MHz) for stability.
- Set sccb_i2c_port = 1 to avoid conflict with IMU Wire (I2C0).
- Initialize **camera first**, then IMU.
- Recommended starting params: QVGA, low FPS, and adjust jpeg_quality for bandwidth.

Settings (copyable)
~~~
pin_pwdn=-1
xclk_freq_hz=20000000
sccb_i2c_port=1
init_order=Camera->IMU
~~~

This document defines the specifications required to implement a system that uses **M5Stack AtomS3R Cam M12 (OV3660)** as a wearable camera to detect goosebumps (piloerection) on skin.  
It covers the full pipeline: **data acquisition**, **pre-validation (FFT gate)**, **(optional) training/analysis**, and **final on-device deployment**.  
The spec assumes role separation between implementers and operators and details **interfaces, data formats, UI requirements, logging requirements, validation gates, and acceptance criteria**.

> v1.4 improves Collector PC setup guidance for Windows and migrates dependency management to uv (uv sync / uv run).
> - Added `collector/pyproject.toml` so environments can be reproduced with `uv sync`
> - Clarified **PlatformIO-based Atom firmware** spec (HTTP upload + UDP control)
> - Formalized **BMI270 (IMU) values bundled per frame** and I2C init/pin rules
> - Reflected Collector UI additions: **Ping / Start/Stop Stream / set_param**
> - Documented `tools/` (simulate / validate / make_labels)

---

## 0. Reference Implementation (Source of Truth)

This spec v1.4 assumes the following reference implementation (included code).  
If you delegate implementation, align behavior to this reference first.

- Collector PC (FastAPI + Web UI): `collector/`
  - Entry point: `collector/app/main.py`
  - UI: `collector/app/ui/index.html`
- AtomS3R-M12 firmware (PlatformIO): `firmware/atoms3r_m12_streamer/`
  - Config: `firmware/atoms3r_m12_streamer/include/user_config.h`
  - Pin definition: `firmware/atoms3r_m12_streamer/include/board_atoms3r_m12_pins.h`
- Ops tools: `tools/`
  - `simulate_device.py` (test /upload without device)
  - `validate_session.py` (session consistency check)
  - `make_labels.py` (events -> labels)

---

## 1. Scope

### 1.1 Goals
1. With a fixed-arm rig, LED lighting, and light blocking, acquire and store skin video stably.
2. While collecting, support **real-time receiving**, **real-time labeling (event logs)**, and **manual LED brightness control**.
3. Immediately after collection, judge detectability using **FFT-based goosebumps index (gb_index)** and a **gate** to avoid GIGO.
4. After passing the gate, proceed to training, quantization, and edge inference if needed.

### 1.2 Non-goals (Not required in v1.4)
- Automatic ROI tracking (fixed rig assumed)
- Medical diagnosis or clinical quality guarantee
- Full generalization across individuals (establish observability and gate first)

---

## 2. System Architecture

### 2.1 Components
- **Device (AtomS3R-M12)**
  - Capture camera frames (JPEG)
  - Read IMU (BMI270) per frame
  - Send frames to PC (HTTP POST multipart)
  - Receive control commands from PC (UDP JSON: LED, start/stop, params)
- **Collector PC**
  - Receive server (HTTP)
  - UI (local web UI)
  - Save data (dataset schema)
  - Compute quality metrics (exposure, blur, banding, motion_flag)
  - FFT-based pilot gate (pilot_report)
- **Analysis (optional)**
  - Expand `events.csv -> labels.csv`
  - Train/evaluate if needed

---

## 3. Network and API Spec

### 3.1 Device -> Collector (HTTP)

#### 3.1.1 `POST /upload` (multipart/form-data)
- `image`: JPEG (filename `frame.jpg`)
- `frame_id`: int (sequence)
- `device_ts_ms`: int (device millis)
- `width`, `height`: int
- `led_pwm`: int (optional; current external LED)

**IMU (optional, implemented in v1.2)**
- `ax, ay, az`: float (units per library; treat as relative)
- `gx, gy, gz`: float (units per library)
- `g_norm`: float (`sqrt(gx^2+gy^2+gz^2)`)

Collector adds `pc_rx_ts_ms` on receipt and uses it for storage and UI.

### 3.2 Collector -> Device (UDP JSON)

#### 3.2.1 Purpose
- Control LED brightness in real time
- Start/stop streaming
- Adjust JPEG quality and FPS
- Ping

#### 3.2.2 Important Note
Collector uses the source IP of `/upload` as the device IP.  
Therefore **the device must upload at least one frame** before `/device/cmd` can succeed.

#### 3.2.3 Commands (v1.2)
- `{"cmd":"ping"}`
- `{"cmd":"set_led","pwm":128}` (0-255)
- `{"cmd":"start_stream"}`
- `{"cmd":"stop_stream"}`
- `{"cmd":"set_param","jpeg_quality":20,"target_fps":12}`
- `{"cmd":"reboot"}`

Device should reply with JSON if possible (best effort).

### 3.3 Collector API (used by UI)
- `GET /ui/`: UI
- `GET /latest.jpg`: latest frame (preview)
- `GET /session`: current status (fps, device_ip, baseline, last_imu, last_quality, etc.)
- `POST /session/start`: start session (create meta.json, log session_start)
- `POST /session/stop`: stop session (log session_stop)
- `POST /event`: record events (goose_on/off, etc.)
- `POST /pilot/calibrate`: compute baseline (last window_sec)
- `POST /pilot/report`: generate pilot_report (AUC, FPR, plot)
- `POST /device/cmd`: send UDP command to device

---

## 4. Data Specification (Storage)

### 4.1 Directory Layout (per session)
```
dataset/
  subject_<ID>/
    <YYYY-MM-DD>_session_<NN>/
      meta.json
      frames/
        000000.jpg
        ...
      frames.csv
      imu.csv
      events.csv
      quality.csv
      pilot/
        gb_index.csv
        pilot_report.json
        pilot_plot.png
      labels.csv   (optional; generated by events)
```

### 4.2 frames.csv (Implementation Notes)
- Rows with `drop_flag=1` indicate retransmits/duplicates; implementation leaves `filename` empty.
- Exclude `drop_flag=1` rows in analysis.

### 4.3 imu.csv
- Implemented in v1.2 (one sample per frame, keyed by frame_id)
- If IMU is unavailable, values may be NaN or rows may be missing.

---

## 5. Device (AtomS3R-M12) Implementation Spec (PlatformIO)

### 5.1 Project Structure
- Location: `firmware/atoms3r_m12_streamer/`
- PlatformIO config: `platformio.ini`
- Editable settings: `include/user_config.h`

### 5.2 Required Config (user_config.h)
- Wi-Fi: `WIFI_SSID`, `WIFI_PASS`
- Collector: `COLLECTOR_HOST`, `COLLECTOR_PORT`, `COLLECTOR_PATH`
- UDP: `UDP_CMD_PORT`
- LED: `LED_PWM_PIN`, `LED_PWM_FREQ_HZ`, `LED_PWM_DEFAULT`

### 5.3 PlatformIO Build (Key Points)
- Use `board_build.arduino.memory_type = qio_opi` for ESP32-S3 + PSRAM
- Dependencies (lib_deps)
  - ArduinoJson v7
  - SparkFun BMI270 Arduino Library (IMU)

### 5.4 Pin Spec (v1.2)
Defined in `include/board_atoms3r_m12_pins.h`.  
- Camera (OV3660): CAM_SDA/CAM_SCL, VSYNC/HREF/PCLK, Y2..Y9, XCLK, PWDN  
- IMU (BMI270): I2C uses **SYS_SDA=GPIO45**, **SYS_SCL=GPIO0**  
  - Always call `Wire.begin(IMU_PIN_SDA, IMU_PIN_SCL)` explicitly.

### 5.5 IMU (v1.2)
- I2C addr: 0x68 (primary)
- Call `getSensorData()` before sending each frame and include ax..gz.
- Continue streaming even if IMU init fails (send NaN or omit).

### 5.6 LED Control (External Lighting)
- PWM control of external LED (rig lighting)
- PWM frequency affects banding; expose `LED_PWM_FREQ_HZ` for tuning

### 5.7 Error Handling (Minimum)
- Reconnect on Wi-Fi disconnect and resume streaming
- Use light backoff on HTTP send failure
- Restart on camera init failure (ESP.restart)

---

## 6. Collector PC Implementation Spec (FastAPI + Web UI)

### 6.1 Startup (Implementation-Aligned)

Collector PC defines dependencies in `collector/pyproject.toml` and uses **uv**.

```powershell
cd collector
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

UI: `http://localhost:8000/ui/`

Notes:
- `uv sync` creates `.venv/` and `uv.lock` (first run).
- `uv run` avoids manual activate steps across shells.

### 6.2 Config Load Rules (Implementation)
Collector searches for `config.yaml`, then falls back to `config_example.yaml`:
- current, parent, grandparent directories

### 6.3 UI (v1.2 Implemented)
- Preview (latest image)
- Session start/stop
- Events (goose/stim/confound/note)
- LED slider + `set_led`
- Pilot (Calibrate / Report)
- **IMU display** (ax/ay/az, gx/gy/gz, g_norm)
- **Quality display** (luma_mean, blur, satW/satB, banding, motion_flag)
- **Device controls**
  - Ping
  - Start/Stop Stream
  - Apply (set_param) with target_fps/jpeg_quality

### 6.4 Quality Metrics and motion_flag (Implementation)
- motion_flag is set based on `blur_laplacian_var` and `g_norm` (either beyond threshold)
- Thresholds are in `config.yaml` (`quality.blur_threshold`, `quality.imu_gnorm_threshold`)

---

## 7. Pilot (FFT Gate) Spec

### 7.1 Calibrate
- UI/API `pilot/calibrate` computes baseline mean/std from the latest window (default 10 sec) of gb_index and sets `mean + k*std`.

### 7.2 Report (Gate Decision)
- Positive interval: `stim_on` to `stim_off`
- Baseline interval: first `calib_start` to `calib_done`
- Confounds:
  - `confound_motion_start` to `confound_motion_stop`
  - `confound_light_start` to `confound_light_stop`

Computed:
- AUC (pos vs baseline)
- baseline_sd / drift
- false positives during confounds (rising edges / min)

Outputs:
- `pilot/gb_index.csv`
- `pilot/pilot_report.json`
- `pilot/pilot_plot.png`

---

## 8. Tools (tools/)

### 8.1 simulate_device.py
Validates Collector receive/save/UI without hardware.  
- Sends mock JPEG and IMU via `/upload`.

### 8.2 validate_session.py
- Verifies required files, row counts, pilot outputs, session_start/stop.

### 8.3 make_labels.py
- Expands `events.csv` goose_on/off into `labels.csv` using `frames.csv` pc_rx_ts_ms.

---

## 9. Acceptance Criteria

### 9.1 Minimum (P0)
- Collector runs and `simulate_device.py` updates preview.
- After session start, frames/ and frames.csv/events.csv/quality.csv are created.

### 9.2 Hardware (P1)
- Atom sends frames and Collector UI shows device_ip.
- UI `Ping` / `set_led` works (LED changes and events.csv logs).
- IMU (if connected) shows g_norm and changes with motion.

### 9.3 Pilot (P2)
- Calibrate sets baseline threshold.
- Report generates pilot_report.json and gate.pass.

---

## 10. Files Needed for Next Steps (Planning)

- **Up to gate decision**: `meta.json`, `frames.csv`, `frames/`, `events.csv`, `quality.csv`, `pilot/*`
- **If training**: above + `labels.csv` (from make_labels)
- **If embedding**: trained model, quantized model, inference log spec

---

## Update v1.3: Auto Luma (Collector Auto Brightness)

- Collector UI `Auto Luma` keeps ROI mean luminance near target by adjusting LED PWM.
- API: `POST /lighting/auto` `{enabled: bool}`
- Adjustments send UDP `{"cmd":"set_led","pwm":...}` **fire-and-forget** to minimize latency.
- When enabled, events.csv logs `led_pwm (note=auto_luma)`.
- UI preview shows a fixed ROI box (CSS overlay).
