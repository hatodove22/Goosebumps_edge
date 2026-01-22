# Goosebumps Hub (PC Viewer + Control + OSC Relay)

Goosebumps Hub は **AtomS3R-CAM の推論状態を可視化・制御**し、  
**OSCイベントを外部アプリへ中継**するPCアプリです。  
対象ファームは `firmware/atoms3r_cam_realtime_infer/` です。

---

## 1. セットアップ（uv推奨）

### 1) 依存関係のインストール
```powershell
cd goosebumps_hub
uv sync
```

### 2) 起動
```powershell
uv run uvicorn hub.app:app --host 0.0.0.0 --port 8000
```

### 3) UIを開く
- `http://localhost:8000/`

> Collectorも同じ 8000 を使うため、同時起動する場合はどちらかのポートを変更してください。

---

## 2. 使い方（基本）

1. UIの **Add Device** で Atom のIP/Port（通常80）を登録  
2. Statusが更新されることを確認  
3. 必要に応じて **Start Run** でログ保存開始  
4. OSCを使う場合は **Enable OSC** と送信先を設定

> Atom側は `/status` / `/control` / `/snapshot` を実装している必要があります。

---

## 3. ログ出力

`Start Run` で `out/<session_id>/` に保存されます。

- `infer.csv`（推論の時系列）
  - `t_pc_iso,t_pc_ms,device_id,t_ms,frame_id,p_raw,p_ema,z,state,rssi,fps,camera_enabled,infer_enabled,use_zscore`
- `pred_events.csv`（state変化イベント）
  - `t_pc_iso,t_pc_ms,device_id,event,t_ms,frame_id,p_ema,z`

---

## 4. OSC配信（イベントのみ）

送信先を複数登録できます。  
送信されるアドレスは以下（デフォルト）:

- `/goose/event` : string `"on"` / `"off"`
- `/goose/event_on` : int 1
- `/goose/event_off` : int 1

> 連続値（p_ema / z）のOSC送信は現行未実装です。

---

## 5. Collector共存（任意）

Atomが `/upload` / `/event` をこのHubに送っている場合、  
Hubはそれらを **Collectorへ転送**できます。

### 環境変数
```
HUB_COLLECTOR_PROXY_BASE_URL="http://192.168.137.1:8002"
HUB_COLLECTOR_PROXY_TIMEOUT_SEC="2.0"
```

### 実行例
```powershell
# Windows (PowerShell)
$env:HUB_COLLECTOR_PROXY_BASE_URL="http://192.168.137.1:8002"
uv run uvicorn hub.app:app --host 0.0.0.0 --port 8000
```

設定が無い場合は 200 OK を返して破棄します（デバイス側の再送防止）。

---

## 6. API概要

- `GET /` : UI
- `GET /ws` : WebSocket（ライブ更新）
- `GET /api/devices`
- `POST /api/devices` `{device_id, host, port}`
- `DELETE /api/devices/{device_id}`
- `POST /api/devices/{device_id}/control`
- `GET /api/devices/{device_id}/snapshot`
- `POST /api/run/start` / `POST /api/run/stop`
- `GET /api/osc/config` / `POST /api/osc/config`
- `GET /api/poll_hz` / `POST /api/poll_hz`

詳細は `docs/goosebumps_spec_v0_3.md` を参照してください。
