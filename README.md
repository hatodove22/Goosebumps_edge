# goosebumps-edgeai

Wearable camera + edge AI system for goosebumps (piloerection) detection.

This repository currently includes a **working Collector PC** implementation (FastAPI):
- Receives JPEG frames from a device via `POST /upload`
- Saves session data in a fixed dataset structure
- Provides a local Web UI for preview, labeling (event logging), LED control (UDP JSON), and pilot FFT gate
- Generates a pilot report (`pilot_report.json` + plot) to avoid GIGO before labeling/ML

It also includes firmware for **M5Stack AtomS3R-M12 (OV3660)** under `firmware/atoms3r_m12_streamer`:
- Streams JPEG frames to the collector
- Accepts UDP JSON commands for LED and streaming control
- (Optional) reads the on-board BMI270 IMU and attaches `ax,ay,az,gx,gy,gz,g_norm` to each frame

## Quickstart (Collector PC)

### 1) Install
```bash
cd collector
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open:
- UI: `http://localhost:8000/ui/`

### 3) Test without device (simulator)
In another terminal (with the same venv active):
```bash
python tools/simulate_device.py --host http://127.0.0.1:8000 --fps 8 --seconds 10
```

You should see the preview updating and, if a session is started, data saved under `dataset/`.

## Documentation
- `docs/implementation_spec.md`
- `docs/procedure_manual.md`
- `docs/dataset_schema.md`
- `docs/open_source_release_guide.md`

## License
TBD (add a LICENSE before open-sourcing).


## Added in v1.3
- Auto Luma (PI control) from Collector UI
- ROI overlay on preview
- `docs/test_plan.md` for real-device tests
