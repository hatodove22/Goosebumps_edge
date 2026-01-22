# Goosebumps Hub (PC Viewer + Control + OSC Relay)

Goosebumps Hub is a PC app that **visualizes and controls** the AtomS3R-CAM real-time inference,  
and **relays OSC events** to external apps.  
Target firmware: `firmware/atoms3r_cam_realtime_infer/`.

---

## 1. Setup (uv recommended)

### 1) Install dependencies
```powershell
cd goosebumps_hub
uv sync
```

### 2) Run
```powershell
uv run uvicorn hub.app:app --host 0.0.0.0 --port 8000
```

### 3) Open the UI
- `http://localhost:8000/`

> Collector uses port 8000 as well, so change one of them if you run both.

---

## 2. Basic usage

1. Click **Add Device** and register the Atom IP/Port (default 80)  
2. Confirm status updates  
3. Start logging with **Start Run** if needed  
4. Configure OSC targets and enable **Enable OSC**

> Atom must implement `/status`, `/control`, and `/snapshot`.

---

## 3. Logging

When **Start Run** is active, Hub writes to `out/<session_id>/`.

- `infer.csv` (time series)
  - `t_pc_iso,t_pc_ms,device_id,t_ms,frame_id,p_raw,p_ema,z,state,rssi,fps,camera_enabled,infer_enabled,use_zscore`
- `pred_events.csv` (state transitions)
  - `t_pc_iso,t_pc_ms,device_id,event,t_ms,frame_id,p_ema,z`

---

## 4. OSC (events only)

Default OSC addresses:
- `/goose/event` : string `"on"` / `"off"`
- `/goose/event_on` : int 1
- `/goose/event_off` : int 1

> Continuous value OSC (p_ema / z) is not implemented yet.

---

## 5. Collector coexistence (optional)

If Atom posts `/upload` / `/event` to Hub, Hub can **forward** them to Collector.

### Environment variables
```
HUB_COLLECTOR_PROXY_BASE_URL="http://192.168.137.1:8002"
HUB_COLLECTOR_PROXY_TIMEOUT_SEC="2.0"
```

### Run example
```powershell
$env:HUB_COLLECTOR_PROXY_BASE_URL="http://192.168.137.1:8002"
uv run uvicorn hub.app:app --host 0.0.0.0 --port 8000
```

If not set, Hub returns 200 and discards the payload.

---

## 6. API summary

- `GET /` : UI
- `GET /ws` : WebSocket (live updates)
- `GET /api/devices`
- `POST /api/devices` `{device_id, host, port}`
- `DELETE /api/devices/{device_id}`
- `POST /api/devices/{device_id}/control`
- `GET /api/devices/{device_id}/snapshot`
- `POST /api/run/start` / `POST /api/run/stop`
- `GET /api/osc/config` / `POST /api/osc/config`
- `GET /api/poll_hz` / `POST /api/poll_hz`

See `docs/en/goosebumps_spec_v0_3.md` for details.

