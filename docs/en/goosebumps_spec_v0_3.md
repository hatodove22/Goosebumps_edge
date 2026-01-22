# Goosebumps Hub / AtomS3R-CAM Inference Spec v0.3

Updated: 2026-01-22

This document defines the **current** specification for the AtomS3R-CAM real-time inference firmware and the PC-side **Goosebumps Hub** (viewer/control/OSC).  
Anything not described here is **not implemented** in the current codebase.

---

## 1. Goal and separation

### 1.1 Goals
- Visualize the **goosebumps state** inferred on AtomS3R-CAM (GC0308)
- Control device parameters (camera/inference/thresholds/LED) via UI
- Relay inference events to external systems via OSC

### 1.2 Separation (recommended)
- **Collector**: data collection + labeling
- **Goosebumps Hub**: viewer / control / OSC relay

---

## 2. System overview (current)

```
Device (AtomS3R-CAM, real-time infer)
  └─ HTTP API: /status, /control, /snapshot

PC (Goosebumps Hub)
  └─ Polls /status for UI
  └─ Proxies /control and /snapshot
  └─ OSC event relay
  └─ CSV logging (infer.csv / pred_events.csv)

PC (Collector) [optional]
  └─ Hub can proxy /upload and /event via env var
```

---

## 3. Device HTTP API (AtomS3R-CAM)

### 3.1 GET /status
Returns device state and latest inference as JSON.

Key fields:
- `device_id`, `fw_version`, `uptime_ms`
- `wifi.ip`, `wifi.rssi`
- `camera_enabled`, `infer_enabled`, `upload_enabled`, `use_zscore`
- `params`:
  - `tau_sec`, `thr_on`, `thr_off`
  - `z_tau_sec`, `z_on`, `z_off`
  - `target_fps`, `led_pwm`
- `telemetry`:
  - `enabled`, `host`, `port`, `hz`
- `infer`:
  - `t_ms`, `frame_id`, `p_raw`, `p_ema`, `z`, `state`

Example (excerpt):
```json
{
  "device_id":"atoms3r_cam_01",
  "fw_version":"0.1.0",
  "uptime_ms":123456,
  "wifi":{"ip":"192.168.137.205","rssi":-52},
  "camera_enabled":true,
  "infer_enabled":true,
  "upload_enabled":false,
  "use_zscore":true,
  "params":{"tau_sec":0.8,"thr_on":0.55,"thr_off":0.45,"z_tau_sec":30,"z_on":4.0,"z_off":3.0,"target_fps":12,"led_pwm":120},
  "telemetry":{"enabled":false,"host":"0.0.0.0","port":9001,"hz":0},
  "infer":{"t_ms":123450,"frame_id":8325,"p_raw":0.41,"p_ema":0.38,"z":2.1,"state":0}
}
```

### 3.2 POST /control
Updates device parameters. The response includes `ok` and `status` (updated state).

Accepted fields:
- `camera_enabled`, `infer_enabled`, `upload_enabled`, `use_zscore`
- `params`: `tau_sec`, `thr_on`, `thr_off`, `z_tau_sec`, `z_on`, `z_off`, `target_fps`, `led_pwm`
- `telemetry`: `enabled`, `host`, `port`, `hz`

Example:
```json
{
  "camera_enabled": true,
  "infer_enabled": true,
  "use_zscore": true,
  "params": { "z_on": 4.0, "z_off": 3.0, "tau_sec": 0.8 },
  "telemetry": { "enabled": false }
}
```

### 3.3 GET /snapshot
Returns a ROI JPEG snapshot.  
If camera is disabled, returns `503 camera_disabled`.

---

## 4. Hub (Goosebumps Hub) spec

### 4.1 Responsibilities
- Register and monitor multiple devices (/status polling)
- Visualize inference (Web UI)
- Control parameters (/control proxy)
- Relay inference events via OSC
- Save logs (CSV)

### 4.2 Core APIs
- `GET /` : Web UI
- `GET /ws` : WebSocket (live updates)

**Device management**
- `GET /api/devices`
- `POST /api/devices` `{device_id, host, port}`
- `DELETE /api/devices/{device_id}`
- `POST /api/devices/{device_id}/control` (proxy to /control)
- `GET /api/devices/{device_id}/snapshot` (proxy to /snapshot)

**Run logging**
- `GET /api/run`
- `POST /api/run/start` `{session_id?, note?, out_root?}`
- `POST /api/run/stop`

**OSC**
- `GET /api/osc/config`
- `POST /api/osc/config` `{enabled, targets, addr_event, addr_on, addr_off}`

**Polling rate**
- `GET /api/poll_hz`
- `POST /api/poll_hz` `{poll_hz}`

### 4.3 Log outputs
Saved under `out/<session_id>/`.

- `infer.csv`
  - `t_pc_iso,t_pc_ms,device_id,t_ms,frame_id,p_raw,p_ema,z,state,rssi,fps,camera_enabled,infer_enabled,use_zscore`
- `pred_events.csv`
  - `t_pc_iso,t_pc_ms,device_id,event,t_ms,frame_id,p_ema,z`

### 4.4 OSC (events only)
- `/goose/event` : string `"on"` / `"off"`
- `/goose/event_on` : int 1
- `/goose/event_off` : int 1

> Continuous value OSC (p_ema / z) is not implemented yet.

---

## 5. Collector coexistence (optional)

Hub exposes `/upload` and `/event` as **Collector-compatible endpoints**.  
If `HUB_COLLECTOR_PROXY_BASE_URL` is set, Hub forwards requests to Collector.

```
HUB_COLLECTOR_PROXY_BASE_URL="http://192.168.137.1:8002"
HUB_COLLECTOR_PROXY_TIMEOUT_SEC="2.0"
```

If not set, Hub returns 200 and discards the payload (to avoid device retries).

---

## 6. Current limitations
- Hub does **not** receive UDP telemetry.
- Viewer supports **/snapshot only** (no video stream).
- Hub polls `/status` at a fixed rate (default 5 Hz).

---

## 7. References
- Hub implementation: `goosebumps_hub/hub/app.py`
- Device firmware: `firmware/atoms3r_cam_realtime_infer/`

