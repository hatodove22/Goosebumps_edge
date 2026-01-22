# 鳥肌検出システム 仕様書（更新版 / v0.3）

**目的**：Atom S3R CAM（エッジ）で推論した鳥肌確率・イベントを、PC側で可視化・制御し、**OSCで他実験（Unity/Max/TouchDesigner等）へ配信**できる状態にする。  
**前提**：既存のCollector（データ収集・ラベル付け）を壊さず、実験用途の「Viewer/配信」機能を強化する。

---

## 1. 背景と課題整理（これまでの知見）

### 1.1 ラベル運用の課題
- `goose_on/off` の押し間違い・状態不明により、**goose_offから開始**、**未クローズ**などが発生。
- 参加者によっては **ラベルが反転**している可能性があり、解析で反転仮定が妥当となる例が確認された。

### 1.2 解析・推論の課題
- フレームレベルでは AUC が高い（例：sub10で0.79台）一方、イベント化（区間化）で精度が落ちる。
- 固定閾値によるイベント化は、確率スケールの個人差で破綻しやすい（例：常時ON）。
- **z-score（セッション内ベースライン差分）**を導入するとイベント化が改善するケースがある。

### 1.3 実験統合の課題
- 他実験システムと連携するには、推論結果を**リアルタイム配信**（OSC等）し、**UIで操作**（カメラON/OFF、z-score使用など）できる必要がある。

---

## 2. 更新方針（Collector改修 or 別アプリ）

### 2.1 結論（推奨）
**Collectorは「データ収集・ラベリング」に専念させ、Viewer/OSC配信は別アプリ（Goosebumps Hub）として実装する**ことを推奨する。

### 2.2 理由
- Collectorは研究データの整合性（events.csv等）に直結するため、Viewer機能を同居させると改修リスクが高い。
- Viewer/OSCは実験ごとに要求が変わりやすい（送信先、レート、UI項目）ため、分離が保守しやすい。
- ただし互換性のため、HubからCollectorへ「推論イベント（gb_pred_on/off）」を記録する連携は可能にする。

> 例：運用モード  
> - **収集モード**：Collector + Atom（フレーム保存、手動ラベル）  
> - **実験モード**：Hub + Atom（推論可視化、OSC配信、必要ならCollectorへ記録）

---

## 3. システム構成（全体アーキテクチャ）

```mermaid
flowchart LR
  subgraph Edge[Edge Device: Atom S3R CAM]
    CAM[Camera + ROI] --> FEAT[LBP features]
    FEAT --> LR[LogReg inference]
    LR --> P[p_raw/p_ema]
    P --> EV[Event detection\n(prob or z-score)]
  end

  subgraph PC[PC]
    HUB[Goosebumps Hub\n(Receiver + Viewer + OSC)] --> OSC[OSC to other systems]
    HUB --> LOG[CSV logs\n(infer.csv / pred_events.csv)]
    HUB <--> CTRL[Device Control\n(HTTP/UDP)]
    HUB <--> VIEW[Web Viewer\n(plot + snapshot)]
    COL[Collector (optional)\n(dataset logging + labeling)]
    HUB -->|optional: gb_pred_on/off| COL
  end

  Edge -->|telemetry push (UDP/HTTP)| HUB
  HUB -->|control (HTTP/UDP)| Edge
```

---

## 4. Atom S3R CAM ファームウェア仕様（推論結果の公開）

### 4.1 目的
- 推論結果（確率・状態）を**外部から取得（pull）**できる。
- 推論結果を**PCへ周期送信（push）**できる。
- PCからカメラ/推論/イベント化方式を制御できる。

### 4.2 推論出力（共通フィールド）
- `device_id`：例 `"atoms3r_cam_01"`
- `fw_version`：例 `"v2.1.0"`
- `t_ms`：デバイス起動からのミリ秒（monotonic）
- `frame_id`：推論対象フレームの連番
- `p_raw`：生の確率（0–1）
- `p_ema`：EMA平滑化後確率（0–1）
- `use_zscore`：z-scoreイベント化のON/OFF
- `z`：z-score（use_zscore=falseでも計算してよい。計算しない場合はnull）
- `state`：0/1（イベント化後の鳥肌状態）
- `rssi`：Wi-Fi RSSI（任意）
- `fps`：推論ループの推定fps（任意）

### 4.3 イベント化方式（推奨）
- **mode A: probability hysteresis**
  - ON条件：`p_ema >= thr_on`
  - OFF条件：`p_ema <= thr_off`
- **mode B: z-score hysteresis**
  - zの定義（実装容易版 / 推奨）：  
    `mu = EMA(p_ema)`, `sigma = sqrt(EMA((p_ema-mu)^2))`  
    `z = (p_ema - mu) / max(sigma, eps)`
  - ON条件：`z >= z_on`
  - OFF条件：`z <= z_off`

> 研究解析ではrolling median+MADが強いが、MCU上では計算コストが高いため、まずは **EMA平均・分散ベース**を標準とする。  
> ただし将来、PC側Hubでrobust zを計算してイベント化するモードも用意する（後述）。

### 4.4 Device側の公開方法（必須）
#### (1) Pull API（HTTP）
- `GET /status`
  - 最新推論値、現在設定、カメラ状態をJSONで返す
- `POST /control`
  - カメラON/OFF、推論ON/OFF、z-score使用、閾値、送信先などを更新

#### (2) Push Telemetry（UDP or HTTP）
- UDP: `infer.json` datagram を `telemetry_host:telemetry_port` へ周期送信（例：10Hz）
- 送信レートは `telemetry_hz` で制御（0で停止）

### 4.5 カメラON/OFFの定義
- `camera_enabled=false`：カメラ停止、推論停止（省電力・安全停止）
- `infer_enabled=true`：カメラがONのときに推論ループを回す
- `stream_enabled=true`：Viewer用のスナップショット送信/配信をON（推論とは独立）

### 4.6 Viewer用スナップショット（任意・推奨）
- `GET /snapshot`
  - 最新フレームのROI（例：160×160）をJPEGで返す（低fps、必要時のみ）
- もしくは、`stream_enabled` のときにHubへ低レート（例：2Hz）でJPEG送信

> GC0308でのJPEG化はCPU負荷があるため、初期は「必要なときだけsnapshot」を推奨。

### 4.7 互換性
- 既存のUDPコマンド（例：LED PWMなど）を維持し、`/control` と二重化しても良い。
- カメラ初期化は「リトライ・power-cycle」を標準実装とする（既に有効）。

---

## 5. Goosebumps Hub（PC側 Viewer/Receiver/OSC）仕様

### 5.1 目的
- Atomから推論結果を受信し、リアルタイムに表示・ログ保存する。
- Atomの動作（camera/stream/zscore/閾値）をUIから切り替える。
- 鳥肌イベントをOSCで他アプリへ配信する。
- （任意）Collectorへ推論イベントを記録する。

### 5.2 実装形態（推奨）
- **Python FastAPI** をバックエンド（受信・制御・OSC）
- Web UI（HTML+JS）を同梱、**WebSocket**で推論値をライブ表示
- OSCは `python-osc` 等で送信

### 5.3 受信仕様
- 受信方式：UDP（推奨）またはHTTP POST
- 受信時刻をPC側でも付与：
  - `t_pc_iso`（例：ISO8601）
  - `t_pc_ms`（monotonic）

### 5.4 ログ保存
- `out/<session_id>/infer.csv`
  - columns: `t_ms, t_pc_iso, frame_id, p_raw, p_ema, z, state, rssi, fps, ...`
- `out/<session_id>/pred_events.csv`
  - columns: `event_type (gb_pred_on/off), t_ms_start, t_ms_end, peak_p, peak_z, mean_p, ...`
- UIで `Start Run / Stop Run` を押したときに session_id を決める（手入力 or 自動採番）

### 5.5 Viewer UI 要件（必須）
- デバイス一覧（IP, RSSI, fw_version, last_seen）
- 大きく見える状態表示
  - `state`（ON/OFF）
  - `p_ema`, `z`
- リアルタイムプロット（直近N秒）
  - p_raw / p_ema / z / state
- 制御トグル
  - Camera ON/OFF
  - Stream ON/OFF
  - use_zscore ON/OFF（イベント化の方式）
- 閾値・パラメータ
  - thr_on/off（prob mode）
  - z_on/off（z mode）
  - tau（EMA）
  - telemetry_hz
- Viewer用画像（任意）
  - Snapshot表示（ボタンで取得）
  - 低fpsプレビュー（stream_enabled時）

### 5.6 OSC配信（必須）
#### 送信先設定
- `osc_enabled`（ON/OFF）
- `osc_targets`：複数可（IP:port）
- `osc_rate_hz`：連続値送信レート（例：20Hz、0でイベント時のみ）

#### OSCメッセージ仕様（提案）
- 連続値（任意）
  - `/goose/prob` : float `p_ema`
  - `/goose/z`    : float `z`
  - `/goose/state`: int `state` (0/1)
- イベント
  - `/goose/event` : string `"on"` / `"off"`
  - `/goose/event_on` : int 1（トリガとして）
  - `/goose/event_off`: int 1
- メタ情報（任意）
  - `/goose/device` : string `device_id`
  - `/goose/session`: string `session_id`

> 他実験側で扱いやすいよう、**“state変化イベント” と “連続値” を分けて送れる**設計とする。

### 5.7 Collector連携（任意）
Hubが推論イベントをCollectorへ記録できるようにする：
- `POST <collector>/event` に
  - `event_type = gb_pred_on / gb_pred_off`
  - `note = "mode=zscore;z_on=...;z_off=..."` 等
  - タイムスタンプはデバイス t_ms とPC時刻の両方をnoteに含めてもよい

> Collector側のevents.csvスキーマを壊さない範囲で追加イベント型を許容する。

---

## 6. Collectorの仕様更新（最小限 / 推奨）

Collector自体を大きく改修せず、以下を追加するだけで実験連携が強くなる。

### 6.1 推奨：events.csvに推論イベントを記録可能にする
- `event_type` に `gb_pred_on/off` を追加許可（パース側で未知イベントを拒否していないことが前提）
- UIは従来どおり手動ラベル中心のまま

### 6.2 Viewer機能はHubへ委譲（推奨）
- Collector UIは「収集・ラベル」のUI改善（状態可視化、冪等トグル等）に集中
- 実験向けViewer・OSCはHubで提供

---

## 7. 制御API詳細（提案）

### 7.1 Atom HTTP API

#### GET /status（例）
```json
{
  "device_id":"atoms3r_cam_01",
  "fw_version":"v2.1.0",
  "uptime_ms":123456,
  "wifi":{"ip":"192.168.137.205","rssi":-50},
  "camera_enabled":true,
  "infer_enabled":true,
  "stream_enabled":false,
  "use_zscore":true,
  "params":{
    "tau_sec":0.8,
    "thr_on":0.55, "thr_off":0.45,
    "z_on":4.0, "z_off":3.0,
    "telemetry_hz":10
  },
  "infer":{
    "t_ms":123450,
    "frame_id":8325,
    "p_raw":0.41,
    "p_ema":0.38,
    "z":2.1,
    "state":0
  }
}
```

#### POST /control（例）
```json
{
  "camera_enabled": true,
  "stream_enabled": false,
  "use_zscore": true,
  "params": { "z_on": 4.0, "z_off": 3.0, "tau_sec": 0.8, "telemetry_hz": 10 },
  "telemetry": { "host": "192.168.137.10", "port": 9001 }
}
```

### 7.2 Hub API（例）
- `GET /devices`
- `POST /devices/<id>/control`
- `GET /ws`（WebSocket：最新値push）
- `POST /osc/config`
- `POST /run/start`, `POST /run/stop`

---

## 8. z-score使用の範囲（仕様上の明確化）

### 8.1 use_zscore の意味
- **false**：probability hysteresis（thr_on/off）で `state` を生成
- **true**：z-score hysteresis（z_on/off）で `state` を生成

### 8.2 zの定義（実装段階）
- Device実装：EMA平均・分散ベース（軽量）
- Hub実装（任意）：rolling median+MAD（robust）  
  - Deviceが `p_ema` を送れば、Hubでrobust zに切り替え可能
  - その場合、Deviceの `state` を使わずHub側でstate生成してOSC配信するモードを用意する

> 設計として「Deviceでstateを作るモード」と「PCでstateを作るモード」を両対応可能にする。

---

## 9. テスト計画（受け入れ基準）

### 9.1 Atom側（ファーム）
- 起動後に `/status` が応答し、推論値が更新され続ける
- `telemetry_hz>0` でUDP送信され、PC側で受信できる
- `camera_enabled=false` にすると推論が止まり、再ONで復帰する
- `use_zscore` のON/OFFで `state` の生成方式が切り替わる
- カメラ初期化失敗時にリトライし、復帰できる（既に確認済み）

### 9.2 Hub側
- 受信した推論値がUIに表示され、CSVに追記される
- OSCが指定ターゲットへ送られる
- ON/OFFイベントが一度だけ送られる（チャタリングしない）
- 連続値送信レートが設定通りになる
- Snapshotが取得できる（実装する場合）

### 9.3 Collector連携（任意）
- Hubから`gb_pred_on/off`を送るとevents.csvへ追記される
- 既存のラベルUIと干渉しない

---

## 10. 実装タスク分解（次にやること）

### 10.1 Atomファーム（必須）
1. `/status` 実装（最新推論の公開）
2. `/control` 実装（camera/stream/use_zscore/閾値/telemetry先）
3. Telemetry push（UDP推奨）実装
4. 既存UDPコマンドとの整合（共存 or 移行）

### 10.2 Hub（必須）
1. UDP/HTTP受信 → WebSocket配信 → CSVログ
2. Viewer UI（状態・プロット・制御）
3. OSC配信（イベント + 連続値、複数ターゲット）
4. session_id 管理（run start/stop）

### 10.3 Collector（最小・任意）
1. `gb_pred_on/off` を受け入れる（イベントタイプ拡張）
2. 推論イベントの表示（任意）

---

## 11. オープン項目（決めておくと実装が速い）

1. **Video/画像をViewerでどこまで見せるか**
   - A: snapshotのみ（最小）
   - B: 低fpsプレビュー（2–5Hz）
   - C: 常時ストリーム（負荷大）

2. **タイムスタンプ基準**
   - Device `t_ms` を主軸、PC受信時刻は補助  
   - 実験同期が重要なら NTP同期やPCからの時刻配布も検討

3. **OSCの送信仕様の最終合意**
   - アドレス命名、連続値送信の有無、イベント時のみ送信など

---

## 付録A：推奨デフォルト設定（初期値）

- telemetry
  - `telemetry_hz = 10`
- smoothing
  - `tau_sec = 0.8`
- event mode
  - `use_zscore = true`
  - `z_on = 4.0`, `z_off = 3.0`
- prob mode（予備）
  - `thr_on = 0.55`, `thr_off = 0.45`
- min duration（Device or Hubで実装）
  - `min_on_sec = 0.8`
  - `gap_merge_sec = 0.8`

> 実験ごとに閾値は変えやすいので、UIから即時変更できることが重要。

---

## 付録B：用語
- **p_raw**：フレーム単位の確率
- **p_ema**：平滑化した確率（見かけのノイズ低減）
- **z-score**：セッション内ベースラインとの差を標準化した値
- **state**：鳥肌イベント状態（0/1）
- **OSC**：外部アプリ連携用プロトコル（リアルタイム制御に広く利用）
