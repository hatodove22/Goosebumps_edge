# Goosebumps (Piloerection) Edge AI System - Procedure Manual v1.4

Updated: 2026-01-16

This manual defines a standardized procedure so first-time implementers and operators can **collect reproducible data** and run **pre-validation (FFT gate)** consistently, from preparation through operation, judgment, and handoff.  
Readers are assumed to share the research goal (goosebumps detection).

> v1.4 adds Windows (PowerShell) setup steps and uv-based dependency management (uv sync / uv run).

Related: `docs/en/implementation_spec.md`

---

## 1. Role Split (Recommended)
- **Developer**
  - Set up the Collector PC (receiver, UI, storage, pilot)
  - Build and flash Atom firmware (PlatformIO)
  - Troubleshoot network, dependencies, I2C, etc.
- **Operator**
  - Attach the rig to the subject (fixture, light blocking)
  - Adjust LED and perform labeling (goose/stim/confound)
  - Record session metadata
- **Analyst**
  - Select gate-pass sessions, generate labels.csv, analyze

---

## 2. First-Time Setup (Collector PC)

Collector PC (FastAPI UI) uses **uv** to manage dependencies and the virtual environment (`.venv/`).

### 2.0 Preconditions
- OS: Windows 10/11 (PowerShell recommended) or macOS/Linux
- Network: Atom and Collector PC can join the same LAN
- Default port: `8000` (if changed, keep UI launch and firmware config consistent)

### 2.1 Install uv (Windows recommended)
**Windows (PowerShell)**

```powershell
# Recommended: WinGet
winget install --id=astral-sh.uv -e

# Alternative: Official installer (PowerShell script)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

> Verify with `uv --version`.

**macOS / Linux (reference)**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2.2 Install dependencies (create .venv)
```powershell
cd collector
uv sync
```

- First run creates `collector/.venv/` and `collector/uv.lock`.
- If Python is not installed, uv can provision it (network required).  
  You can also pin a version manually with `uv python install 3.11`.

### 2.3 Run (uv run recommended)
```powershell
cd collector
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

UI: `http://localhost:8000/ui/`

> On Windows, firewall rules may be needed for inbound `8000/tcp`.

### 2.4 Smoke Test without Device (Recommended)
```powershell
cd collector
uv run python ../tools/simulate_device.py --host http://127.0.0.1:8000 --fps 8 --seconds 10
```

- UI Preview updates
- If a session is running, data is saved under dataset/

### 2.5 Troubleshooting (Network)
- "Invalid HTTP request received" on phone/browser  
  - **Use http:// explicitly** (not HTTPS)
- When using Windows mobile hotspot, COLLECTOR_HOST  
  - Example: 192.168.137.1 (hotspot host IP)

Reference (copy)
~~~
http://192.168.137.1:8000/ui/
COLLECTOR_HOST=192.168.137.1
~~~

### 2.6 Atom S3R CAM (non-M12 / GC0308) Hardware Check
- CAMERA_VARIANT=0 (non-M12/GC0308)
- Images are sent as **RGB565 -> software JPEG**  
  - Start with **QVGA + low FPS**
- Camera power and init notes  
  - Keep POWER_N(GPIO18) **LOW**  
  - pin_pwdn = -1 (prevent esp_camera from touching GPIO18)  
  - xclk=20MHz recommended  
  - sccb_i2c_port=1 (avoid conflict with IMU I2C0)  
  - **Init order: Camera -> IMU**

Settings memo (copy)
~~~
CAMERA_VARIANT=0
pin_pwdn=-1
xclk=20MHz
sccb_i2c_port=1
init_order=Camera->IMU
~~~

## 3. AtomS3R-M12 (PlatformIO) Setup

### 3.1 Edit config
Edit `firmware/atoms3r_m12_streamer/include/user_config.h`.
- Wi-Fi SSID/PASS
- Collector host IP (PC IP)
- LED PWM pin (external LED)

### 3.2 Flash
```bash
cd firmware/atoms3r_m12_streamer
pio run -t upload
pio device monitor
```
Check Serial for:
- Wi-Fi connect success and IP
- Camera init OK
- IMU init OK (if connected)

---

## 4. Pre-Experiment Setup (Every Session)

### 4.1 Physical Mounting
1. Fix camera position (distance/rotation) with the rig
2. Block light with black cloth (cover outside the FOV)
3. Fix cables so tension does not affect the rig
4. Ensure LED is not in the subject's direct view

### 4.2 Collector UI Preparation
1. Open UI (`/ui/`)
2. Confirm skin is centered in ROI in Preview
3. If device_ip does not appear yet, Atom may not be sending `/upload`

---

## 5. Device Operations (v1.2 UI)

### 5.1 Ping (Connectivity)
- device_ip appears after at least one upload from Atom.
- Confirm response with the `Ping` button.

### 5.2 Start/Stop Stream
- Optional operation: stop before experiment, then start when ready.

### 5.3 Parameter Tuning (if Wi-Fi is unstable)
- Increase `jpeg_quality` (more compression) to reduce bandwidth.
- Reduce `target_fps` to reduce dropouts.
- Use UI `Apply Params` to send `set_param`.

---

## 6. Lighting Adjustment (LED)

### 6.1 Manual Adjustment
- Use LED slider to adjust brightness.
- Check Quality display: choose a range where satW/satB are small.
- If banding is strong, consider changing PWM frequency (firmware).

---

## 7. Pre-Validation (FFT Gate) Protocol (Required)

Goal: **Decide if goosebumps features are separable before heavy labeling/training.**

### 7.1 Segment Composition (3 parts)
- Negative (rest)
- Positive (certain induction, cold stimulus, safety first)
- Confound (motion/light variation)

### 7.2 Procedure
#### Step A: Start session
- Enter subject/operator and click `Start`

#### Step B: Baseline (Calibrate)
- Rest and run `Calibrate (10s)`
- Baseline and threshold are shown

#### Step C: Positive
- Start stimulus with `Stim ON` (S)
- When goosebumps appear, `Goose ON` (G), and `Goose OFF` when it subsides
- End stimulus with `Stim OFF`

#### Step D: Confound
- `Confound Motion` (M) for light motion
- `Confound Light` (L) for large LED change (short)

#### Step E: Report
- Press `Generate Report`
- Check gate.pass in `pilot_report.json`

---

## 8. IMU Check (v1.2)

### 8.1 UI Check
- IMU field shows numeric `g_norm` (not `-` or NaN)
- Move the arm and confirm g_norm changes and motion becomes YES

### 8.2 If IMU Is Not Shown
- Check Serial for `[IMU] BMI270 connected`
- Check I2C pins (SYS_SDA=GPIO45, SYS_SCL=GPIO0)
- Check wiring/contacts, I2C pull-ups, power

---

## 9. Post-Session Verification and Backup

### 9.1 Session Validation (Recommended)
```bash
python tools/validate_session.py dataset/subject_001/2026-01-15_session_01
```
- Required files exist
- frames count and CSV consistency
- pilot generated
- session_start/stop exist

### 9.2 Backup
- Copy `dataset/subject_xxx/` to another medium right after collection.

---

## 10. Handoff to Analyst

### 10.1 Generate labels.csv
```bash
python tools/make_labels.py dataset/subject_001/2026-01-15_session_01
```
- Expand goose_on/off events into labels.csv.

### 10.2 Minimal Handoff Set
- `meta.json`
- `frames/` + `frames.csv`
- `quality.csv`
- `events.csv`
- `pilot/` (includes pilot_report.json)
- `labels.csv` (if training)

---

## Update v1.4: Logging, Analysis, and Edge Inference Flow

See `docs/en/analysis_and_edge_methods.md` for details.

### Analysis flow (minimum)
1. Validate session with `tools/validate_session.py`
2. Run `Generate Report` in UI to confirm FFT gate (GIGO avoidance)
3. Generate `labels.csv` with `tools/make_labels.py`
4. Use `tools/derive_features.py` to check features and AUC/mean gap

### Additional (Plan B: LBP+LR)
- Train: `tools/train_lbp_lr.py` (model JSON)
- Infer: `tools/infer_lbp_lr.py` (session-level check)
- Export: `tools/export_lbp_lr_header.py` (firmware header)

Windows (uv) examples:
```powershell
cd collector
uv run python ../tools/derive_features.py ../dataset/subject_001/2026-01-16_session_01
uv run python ../tools/train_lbp_lr.py --dataset-root ../dataset --out ../models/lbp_lr_model.json --require-motion-ok
uv run python ../tools/export_lbp_lr_header.py --model ../models/lbp_lr_model.json --out ../firmware/atoms3r_m12_streamer/include/model_lbp_lr.h
```

---

## Update v1.3: Auto Luma and ROI Box

- Turning ON `Auto Luma` in Lighting auto-adjusts LED PWM.
- Auto-follow PWM is logged in events.csv as `led_pwm (note=auto_luma)`.
- Preview shows a fixed ROI box. Adjust the rig so skin stays in the ROI.
- For on-device tests, see `docs/en/test_plan.md`.
