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

## Supported hardware
- AtomS3R-M12 (OV3660, M12)
- AtomS3R-CAM (GC0308, non-M12)

## Docs
- `docs/procedure_manual.md`
- `docs/implementation_spec.md`
- `docs/lab_log/`
- `docs/dataset_schema.md`
- `docs/open_source_release_guide.md`

## Quickstart (Collector PC)

Collector PC は **uv**（AstralのPythonパッケージ/プロジェクトマネージャ）で環境を作成します。

### 0) uv をインストール

**Windows (PowerShell)**
```powershell
winget install --id=astral-sh.uv -e
# もしくは（公式インストーラ）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1) 依存関係をインストール（.venv を作成）
```powershell
cd collector
uv sync
```

> `uv sync` により、プロジェクト直下に `.venv/` と `uv.lock` が生成されます（初回のみ）。

### 2) 起動（uv run 推奨）
```powershell
cd collector
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open UI:
- `http://localhost:8000/ui/`

### 3) 実機なしスモークテスト（擬似デバイス）
別ターミナルで：
```powershell
cd collector
uv run python ../tools/simulate_device.py --host http://127.0.0.1:8000 --fps 8 --seconds 10
```

データ保存を確認する場合は、UIで Session Start を押してから実行してください。
## License
TBD (add a LICENSE before open-sourcing).


## Added in v1.3
- Auto Luma (PI control) from Collector UI
- ROI overlay on preview
- `docs/test_plan.md` for real-device tests







