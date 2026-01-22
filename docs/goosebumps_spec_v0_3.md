# Goosebumps Hub / AtomS3R-CAM 推論 仕様書 v0.3

更新日: 2026-01-22

本書は、**AtomS3R-CAMのリアルタイム推論**と、**PC側の可視化・制御・OSC配信（Goosebumps Hub）**を統合して運用するための仕様を、**現行実装に合わせて**整理したものである。

> 収集・ラベリングは Collector、可視化/OSC は Hub に分離する前提。  
> ここに書かれていない機能は **現行実装には存在しない**（古い案は削除）。

---

## 1. 目的と分離方針

### 1.1 目的
- AtomS3R-CAM（GC0308）で推論した**鳥肌状態**をPCで可視化する
- 端末制御（カメラ/推論/閾値/LED）をUIから行えるようにする
- 推論イベントをOSCで他システム（Unity/Max/TouchDesigner等）に配信する

### 1.2 分離方針（推奨）
- **Collector**: データ収集・ラベリングに専念
- **Goosebumps Hub**: Viewer / Control / OSC 配信

---

## 2. システム構成（現行）

```
Device (AtomS3R-CAM, real-time infer)
  └─ HTTP API: /status, /control, /snapshot

PC (Goosebumps Hub)
  └─ /status を定期ポーリングしてUI表示
  └─ /control でパラメータ更新
  └─ /snapshot でROIの静止画取得
  └─ OSCイベント配信
  └─ CSVログ出力 (infer.csv / pred_events.csv)

PC (Collector) [任意]
  └─ Hubが /upload /event を代理受信・転送（環境変数で有効化）
```

---

## 3. Device HTTP API（AtomS3R-CAM側）

### 3.1 GET /status
デバイス状態と最新推論値をJSONで返す。

主なフィールド:
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

例（抜粋）:
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
デバイスのパラメータを更新する。レスポンスに `ok` と `status`（更新後の状態）を返す。

指定可能な項目:
- `camera_enabled`, `infer_enabled`, `upload_enabled`, `use_zscore`
- `params`: `tau_sec`, `thr_on`, `thr_off`, `z_tau_sec`, `z_on`, `z_off`, `target_fps`, `led_pwm`
- `telemetry`: `enabled`, `host`, `port`, `hz`

例:
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
ROIの静止画を JPEG で返す。  
カメラ無効時は `503 camera_disabled`。

---

## 4. Hub（Goosebumps Hub）仕様

### 4.1 役割
- 複数デバイスの登録・監視（/status ポーリング）
- 推論値の可視化（Web UI）
- パラメータ制御（/control 送信）
- 推論イベントのOSC配信
- ログ保存（CSV）

### 4.2 主要API
- `GET /` : Web UI
- `GET /ws` : WebSocket（UIへのライブ更新）

**デバイス管理**
- `GET /api/devices`
- `POST /api/devices` `{device_id, host, port}`
- `DELETE /api/devices/{device_id}`
- `POST /api/devices/{device_id}/control`（/control へproxy）
- `GET /api/devices/{device_id}/snapshot`（/snapshot へproxy）

**Runログ**
- `GET /api/run`
- `POST /api/run/start` `{session_id?, note?, out_root?}`
- `POST /api/run/stop`

**OSC**
- `GET /api/osc/config`
- `POST /api/osc/config` `{enabled, targets, addr_event, addr_on, addr_off}`

**ポーリング周期**
- `GET /api/poll_hz`
- `POST /api/poll_hz` `{poll_hz}`

### 4.3 ログ出力
`out/<session_id>/` に保存される。

- `infer.csv`（推論の時系列）
  - `t_pc_iso,t_pc_ms,device_id,t_ms,frame_id,p_raw,p_ema,z,state,rssi,fps,camera_enabled,infer_enabled,use_zscore`
- `pred_events.csv`（state変化イベント）
  - `t_pc_iso,t_pc_ms,device_id,event,t_ms,frame_id,p_ema,z`

### 4.4 OSC配信（現行はイベントのみ）
- `/goose/event` : string `"on"` / `"off"`
- `/goose/event_on` : int 1
- `/goose/event_off` : int 1

> 連続値（p_ema / z）のOSC送信は現行未実装。

---

## 5. Collector共存（任意）

Hubは `/upload` と `/event` を**Collector互換の受け口**として持つ。  
環境変数 `HUB_COLLECTOR_PROXY_BASE_URL` を設定すると、  
受けたリクエストをCollectorへ**生転送**する。

```
HUB_COLLECTOR_PROXY_BASE_URL="http://192.168.137.1:8002"
HUB_COLLECTOR_PROXY_TIMEOUT_SEC="2.0"
```

設定が無い場合、Hubは200を返して破棄する（デバイスの再送防止）。

---

## 6. 現行の制約・注意
- Hubは**UDPテレメトリ受信を持たない**（Deviceが送信してもHubは受けない）。
- Viewerの画像表示は**/snapshotのみ**（動画ストリームは未対応）。
- Hubは `/status` を **ポーリング**で取得する（デフォルト5Hz）。

---

## 7. 参照
- Hub実装: `goosebumps_hub/hub/app.py`
- Device実装: `firmware/atoms3r_cam_realtime_infer/`

