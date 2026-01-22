# Goosebumps Edge AI

Wearable camera + edge AI system for goosebumps (piloerection) detection.

This repository includes:

- **Collector PC (FastAPI)**
  - Receives JPEG frames from a device via `POST /upload`
  - Saves session data in a fixed dataset structure
  - Web UI for preview, labeling (event logging), LED control (UDP JSON), and pilot FFT gate
  - Auto Luma (PI control) and ROI overlay to validate data quality before labeling/ML
  - Generates a pilot report (`pilot_report.json` + plot) to avoid GIGO
- **Firmware**
  - `firmware/atoms3r_m12_streamer`: streaming JPEG uploader with UDP JSON control (optional BMI270 IMU)
  - `firmware/atoms3r_cam_realtime_infer`: on-device inference (LBP + Logistic Regression) with optional upload/event posts

## Supported hardware
- AtomS3R-M12 (OV3660, M12)
- AtomS3R-CAM (GC0308, non-M12)

## Repository layout
- `collector/`: Collector PC server + UI
- `firmware/`: device firmware (streamer + real-time inference)
- `tools/`: training/export utilities and simulators
- `docs/`: Japanese docs
- `docs/en/`: English docs
- `examples/`, `hardware/`: references and assets

## Docs
- `docs/en/procedure_manual.md`
- `docs/en/implementation_spec.md`
- `docs/en/analysis_and_edge_methods.md`
- `docs/en/dataset_schema.md`
- `docs/en/test_plan.md`
- `docs/en/open_source_release_guide.md`

(See `docs/` for the Japanese versions.)

## Quickstart (Collector PC)

The Collector uses **uv** (Astral's Python project manager).

### 0) Install uv

**Windows (PowerShell)**
```powershell
winget install --id=astral-sh.uv -e
# or (official installer)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1) Install dependencies (creates `.venv`)
```powershell
cd collector
uv sync
```

> `uv sync` generates `.venv/` and `uv.lock` in the project directory (first run only).

### 2) Run the server (recommended via `uv run`)
```powershell
cd collector
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open UI:
- `http://localhost:8000/ui/`

### 3) Smoke test without hardware (simulated device)
In another terminal:
```powershell
cd collector
uv run python ../tools/simulate_device.py --host http://127.0.0.1:8000 --fps 8 --seconds 10
```

If you want to save data, click **Session Start** in the UI before running the simulator.

## License
TBD (add a LICENSE before open-sourcing).
