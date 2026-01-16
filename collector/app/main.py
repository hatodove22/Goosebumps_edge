from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from fastapi import FastAPI, File, Form, UploadFile, Request
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .state import SessionState
from .pilot_fft import parse_events, make_pilot_report
from .device_udp import send_udp_json

APP_VERSION = "0.1.0-dev"


def load_config() -> Dict[str, Any]:
    # config.yaml in repo root, fallback to config_example.yaml
    candidates = [
        Path("config.yaml"),
        Path("../config.yaml"),
        Path("../../config.yaml"),
        Path("config_example.yaml"),
        Path("../config_example.yaml"),
        Path("../../config_example.yaml"),
    ]
    for p in candidates:
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


app = FastAPI(title="Goosebumps Collector", version=APP_VERSION)

# mount UI static if needed
ui_dir = Path(__file__).parent / "ui"
app.mount("/ui_static", StaticFiles(directory=str(ui_dir)), name="ui_static")

state = SessionState()
state.config = load_config()
state.dataset_root = Path(state.config.get("project", {}).get("dataset_root", "dataset"))


@app.get("/", response_class=HTMLResponse)
def root():
    return "<html><body><h3>Goosebumps Collector</h3><p>Open <a href='/ui/'>/ui/</a></p></body></html>"


@app.get("/ui/", response_class=HTMLResponse)
def ui_index():
    html = (ui_dir / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/latest.jpg")
def latest_jpg():
    if not state.latest_frame:
        return Response(status_code=404)
    return Response(content=state.latest_frame.jpeg, media_type="image/jpeg")


@app.get("/session")
def get_session():
    return {
        "active": state.active,
        "subject_id": state.subject_id,
        "session_id": state.session_id,
        "operator": state.operator,
        "body_site": state.body_site,
        "notes": state.notes,
        "fps": state.last_fps,
        "device_ip": state.last_device_ip,
        "baseline": None if state.baseline is None else {
            "mean": state.baseline.mean,
            "std": state.baseline.std,
            "k": state.baseline.threshold_k,
            "thr": state.baseline.threshold_value,
            "computed_at_pc_ms": state.baseline.computed_at_pc_ms,
        },
        "current_led_pwm": state.current_led_pwm,
        "auto_luma_enabled": state.auto_luma_enabled,
        "last_imu": state.last_imu or None,
        "last_quality": state.last_quality or None,
        "last_gb_index": state.last_gb_index,
    }



class AutoLumaReq(BaseModel):
    enabled: bool


@app.post("/lighting/auto")
def set_auto_luma(req: AutoLumaReq):
    state.auto_luma_enabled = bool(req.enabled)
    if state.auto_luma_enabled:
        state.auto_luma_integral = 0.0
        if state.active and state.storage:
            state.storage.log_event("auto_luma_on", 1, note="")
    else:
        if state.active and state.storage:
            state.storage.log_event("auto_luma_off", 1, note="")
    return {"ok": True, "auto_luma_enabled": state.auto_luma_enabled}


class StartSessionReq(BaseModel):
    subject_id: str
    session_id: Optional[str] = None
    operator: str = ""
    body_site: str = "forearm"
    notes: str = ""


@app.post("/session/start")
def start_session(req: StartSessionReq):
    # generate session_id if not provided
    if not req.session_id:
        date = time.strftime("%Y-%m-%d")
        # find next index
        subj_dir = state.dataset_root / f"subject_{req.subject_id}"
        subj_dir.mkdir(parents=True, exist_ok=True)
        existing = [p.name for p in subj_dir.iterdir() if p.is_dir() and p.name.startswith(date)]
        idx = 1
        while f"{date}_session_{idx:02d}" in existing:
            idx += 1
        session_id = f"{date}_session_{idx:02d}"
    else:
        session_id = req.session_id

    state.start_session(
        subject_id=req.subject_id,
        session_id=session_id,
        operator=req.operator,
        body_site=req.body_site,
        notes=req.notes,
    )
    # update meta.json with config snapshot
    if state.storage:
        meta = {
            "schema_version": "1.0",
            "subject_id": req.subject_id,
            "session_id": session_id,
            "operator": req.operator,
            "body_site": req.body_site,
            "notes": req.notes,
            "created_at_pc_ms": int(time.time() * 1000),
            "camera": state.config.get("camera", {}),
            "roi": state.config.get("roi", {}),
            "lighting": state.config.get("lighting", {}),
            "quality": state.config.get("quality", {}),
            "pilot_fft": state.config.get("pilot_fft", {}),
            "software": {"collector_version": APP_VERSION},
        }
        state.storage.update_meta(meta)
    return {"ok": True, "session_id": session_id}


@app.post("/session/stop")
def stop_session():
    state.stop_session()
    return {"ok": True}


@app.post("/upload")
async def upload(
    request: Request,
    image: UploadFile = File(...),
    frame_id: int = Form(...),
    device_ts_ms: int = Form(...),
    width: int = Form(...),
    height: int = Form(...),
    ax: Optional[float] = Form(None),
    ay: Optional[float] = Form(None),
    az: Optional[float] = Form(None),
    gx: Optional[float] = Form(None),
    gy: Optional[float] = Form(None),
    gz: Optional[float] = Form(None),
    g_norm: Optional[float] = Form(None),
    led_pwm: Optional[int] = Form(None),
):
    jpeg = await image.read()
    pc_rx_ts_ms = int(time.time() * 1000)

    extra: Dict[str, Any] = {}
    for k, v in [("ax", ax), ("ay", ay), ("az", az), ("gx", gx), ("gy", gy), ("gz", gz), ("g_norm", g_norm), ("led_pwm", led_pwm)]:
        if v is not None:
            extra[k] = v

    device_ip = None
    if request.client:
        device_ip = request.client.host

    res = state.handle_upload(
        image_jpeg=jpeg,
        frame_id=int(frame_id),
        device_ts_ms=int(device_ts_ms),
        width=int(width),
        height=int(height),
        extra=extra,
        pc_rx_ts_ms=pc_rx_ts_ms,
        device_ip=device_ip,
    )
    return JSONResponse(res)


class EventReq(BaseModel):
    type: str
    value: Any = 1
    note: str = ""
    pc_ts_ms: Optional[int] = None


@app.post("/event")
def post_event(req: EventReq):
    if state.active and state.storage:
        # pc_ts_ms override if provided (e.g., reaction-delay compensation)
        if req.pc_ts_ms is None:
            state.storage.events_csv.append({
                "pc_ts_ms": int(time.time() * 1000),
                "type": req.type,
                "value": req.value,
                "note": req.note or "",
            })
        else:
            state.storage.events_csv.append({
                "pc_ts_ms": int(req.pc_ts_ms),
                "type": req.type,
                "value": req.value,
                "note": req.note or "",
            })
        return {"ok": True}
    return {"ok": False, "error": "no active session"}


class CalibReq(BaseModel):
    window_sec: float = 10.0
    k_sigma: float = 3.0


@app.post("/pilot/calibrate")
def pilot_calibrate(req: CalibReq):
    stats = state.calibrate_baseline(seconds=req.window_sec, k_sigma=req.k_sigma)
    return {"ok": True, "baseline": {
        "mean": stats.mean, "std": stats.std, "k": stats.threshold_k, "thr": stats.threshold_value, "computed_at_pc_ms": stats.computed_at_pc_ms
    }}


@app.post("/pilot/report")
def pilot_report():
    if not state.session_id or not state.subject_id:
        return {"ok": False, "error": "no session info"}
    if not state.storage or not state.storage.base_dir:
        # allow generating report after stop: infer base_dir
        base_dir = state.dataset_root / f"subject_{state.subject_id}" / state.session_id
    else:
        base_dir = state.storage.base_dir
    events = parse_events(base_dir / "events.csv")
    t_ms, gb_smooth, gb_binary, thr = state.compute_smoothed_and_binary()
    # raw gb
    import numpy as np
    with state.series_lock:
        gb_raw = np.array([x[2] for x in state.gb_series], dtype=np.float32)

    report = make_pilot_report(
        out_dir=base_dir / "pilot",
        session_id=state.session_id,
        t_ms=t_ms,
        gb=gb_raw,
        gb_smooth=gb_smooth,
        gb_binary=gb_binary,
        threshold=thr,
        events=events,
        config=state.config,
    )
    return {"ok": True, "report": report}


class DeviceCmdReq(BaseModel):
    cmd: str
    pwm: Optional[int] = None
    jpeg_quality: Optional[int] = None
    target_fps: Optional[int] = None


@app.post("/device/cmd")
def device_cmd(req: DeviceCmdReq):
    ip = state.last_device_ip
    if not ip:
        return {"ok": False, "error": "device ip unknown (send a frame first)"}
    port = int(state.config.get("network", {}).get("device_udp_cmd_port", 3333))
    payload = req.model_dump(exclude_none=True)
    ok, resp = send_udp_json(ip, port, payload)
    # keep local LED state for UI
    if req.cmd == "set_led" and req.pwm is not None:
        state.current_led_pwm = int(req.pwm)
        if state.active and state.storage:
            state.storage.log_event("led_pwm", int(req.pwm), note="udp_cmd")
    return {"ok": ok, "device_ip": ip, "response": resp}
