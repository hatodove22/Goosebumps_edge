# 鳥肌（立毛）検出エッジAIシステム — 実装仕様書（Implementation Spec） v1.4

更新日: 2026-01-16

本書は **M5Stack AtomS3R Cam M12（OV3660）** をウェアラブルカメラとして用い、皮膚表面の鳥肌（立毛）を検出するためのシステムを、**データ取得**・**事前検証（FFTゲート）**・（必要なら）**学習/解析**・**最終組み込み**まで一貫して実装するための仕様を定義する。  
実装担当者および実験担当者が分業する前提で、**インターフェース、データ仕様、UI要件、ログ要件、検証ゲート、受入条件**を明記する。

> v1.4 では、Collector PC のセットアップを Windows でも迷わないように整理し、uv（uv sync / uv run）による依存関係管理へ移行した。
> - `collector/pyproject.toml` を追加し、`uv sync` で環境を再現できるようにした
> - **PlatformIO想定のAtomファーム**（HTTPアップロード＋UDP制御）仕様を具体化  
> - **BMI270（IMU）値をフレーム送信に同梱**する仕様とピン/I2C初期化を明文化  
> - Collector UIに **Ping / Start/Stop Stream / set_param** 等の操作を追加したことを反映  
> - `tools/`（simulate / validate / make_labels）を仕様として明文化

---

## 0. リファレンス実装（本書の“正”）

本書 v1.2 は、以下のリファレンス実装（同梱コード）を前提にしている。  
第三者に実装委任する場合も、まずはこの実装を基準として動作を揃える。

- Collector PC（FastAPI + Web UI）: `collector/`
  - エントリポイント: `collector/app/main.py`
  - UI: `collector/app/ui/index.html`
- AtomS3R-M12 ファーム（PlatformIO）: `firmware/atoms3r_m12_streamer/`
  - 設定: `firmware/atoms3r_m12_streamer/include/user_config.h`
  - ピン定義: `firmware/atoms3r_m12_streamer/include/board_atoms3r_m12_pins.h`
- 運用ツール: `tools/`
  - `simulate_device.py`（実機なしで /upload を叩く）
  - `validate_session.py`（セッション整合性チェック）
  - `make_labels.py`（events → labels 変換）

---

## 1. スコープ

### 1.1 ゴール
1. 腕固定治具＋LED照明＋遮光下で、皮膚映像を安定に取得・保存できる。
2. 収集と同時に、**リアルタイム受信**、**リアルタイムラベリング（イベントログ）**、**LED輝度調整（手動）**が可能。
3. 収集直後に「FFTベースの鳥肌指標（gb_index）」で **検出可能性（Observability）**を判定し、GIGOを避ける **ゲート判定**ができる。
4. ゲート合格後に、必要に応じて学習・量子化・エッジ推論へ進める。

### 1.2 非ゴール（v1.2では必須としない）
- 自動ROI追跡（固定治具前提）
- 医療用途の診断・臨床品質保証
- すべての個体差に対する完全汎化（まず観測系とゲートを確立）

---

## 2. システム構成

### 2.1 コンポーネント
- **Device（AtomS3R-M12）**
  - カメラ取得（JPEG）
  - IMU（BMI270）取得（各フレーム1サンプル）
  - PCへフレーム送信（HTTP POST multipart）
  - PCからの制御受信（UDP JSON: LED、開始/停止、パラメータ）
- **Collector PC**
  - 受信サーバ（HTTP）
  - UI（ローカルWeb UI）
  - 保存（dataset仕様に従う）
  - 品質メトリクス算出（露出、ブレ、縞、motion_flag）
  - FFTベースのパイロットゲート判定（pilot_report生成）
- **Analysis（任意）**
  - `events.csv → labels.csv` 展開
  - 学習・評価（必要な場合のみ）

---

## 3. ネットワーク・API仕様

### 3.1 Device → Collector（HTTP）

#### 3.1.1 `POST /upload`（multipart/form-data）
- `image` : JPEG（filename `frame.jpg`）
- `frame_id` : int（連番）
- `device_ts_ms` : int（deviceのmillis等）
- `width`, `height` : int
- `led_pwm` : int（任意。外部LEDの現在値）

**IMU（任意、v1.2で実装済み）**
- `ax, ay, az` : float（単位はライブラリ既定。解析はまず相対値として扱う）
- `gx, gy, gz` : float（単位はライブラリ既定）
- `g_norm` : float（`sqrt(gx^2+gy^2+gz^2)`）

Collectorは受信時刻 `pc_rx_ts_ms` を付与し、保存およびUI表示に用いる。

### 3.2 Collector → Device（UDP JSON）

#### 3.2.1 目的
- LED輝度をリアルタイムに操作
- ストリーミング開始/停止
- JPEG品質やFPSなどの送信負荷調整
- 疎通（Ping）

#### 3.2.2 注意（重要）
Collectorは `/upload` の接続元IP（`request.client.host`）を「Device IP」として扱う。  
したがって **Deviceは最低1回フレームを送信してから**でないと、Collector側の `/device/cmd` が成功しない。

#### 3.2.3 コマンド（v1.2実装）
- `{"cmd":"ping"}`
- `{"cmd":"set_led","pwm":128}`（0-255）
- `{"cmd":"start_stream"}`
- `{"cmd":"stop_stream"}`
- `{"cmd":"set_param","jpeg_quality":20,"target_fps":12}`
- `{"cmd":"reboot"}`

Deviceは可能ならJSONで応答を返す（ベストエフォート）。

### 3.3 Collector API（UIが利用）
- `GET /ui/` : UI
- `GET /latest.jpg` : 最新フレーム（UIプレビュー用）
- `GET /session` : 現在状態（fps、device_ip、baseline、last_imu、last_quality等）
- `POST /session/start` : セッション開始（meta.json作成、eventsにsession_start）
- `POST /session/stop` : セッション停止（eventsにsession_stop）
- `POST /event` : イベント記録（goose_on/off等）
- `POST /pilot/calibrate` : ベースライン確定（直近 window_sec）
- `POST /pilot/report` : pilot_report生成（AUC、偽陽性率、plot）
- `POST /device/cmd` : UDPでDeviceへコマンド送信（Ping/LED/Start/Stop/Param）

---

## 4. データ仕様（保存形式）

### 4.1 ディレクトリ（セッション単位）
```
dataset/
  subject_<ID>/
    <YYYY-MM-DD>_session_<NN>/
      meta.json
      frames/
        000000.jpg
        ...
      frames.csv
      imu.csv
      events.csv
      quality.csv
      pilot/
        gb_index.csv
        pilot_report.json
        pilot_plot.png
      labels.csv   (任意。events→展開で生成)
```

### 4.2 frames.csv（実装に合わせた注意）
- `drop_flag=1` の行は **再送/重複**等を示す。実装では `filename` を空にする。
- 解析では `drop_flag=1` を除外して扱う。

### 4.3 imu.csv
- v1.2で実装済み（各フレーム1サンプル、frame_idで紐づけ）
- IMUが取得できない場合は NaN が入る、または該当行が欠けることがある（実装依存）。

---

## 5. Device（AtomS3R-M12）実装仕様（PlatformIO）

### 5.1 プロジェクト構成
- 位置: `firmware/atoms3r_m12_streamer/`
- PlatformIO設定: `platformio.ini`
- 編集する設定: `include/user_config.h`

### 5.2 必須設定（user_config.h）
- Wi-Fi: `WIFI_SSID`, `WIFI_PASS`
- Collector: `COLLECTOR_HOST`, `COLLECTOR_PORT`, `COLLECTOR_PATH`
- UDP: `UDP_CMD_PORT`
- LED: `LED_PWM_PIN`, `LED_PWM_FREQ_HZ`, `LED_PWM_DEFAULT`

### 5.3 PlatformIO build設定（要点）
- ESP32-S3 + PSRAM利用のため、`board_build.arduino.memory_type = qio_opi` を使用
- 依存ライブラリ（lib_deps）
  - ArduinoJson v7
  - SparkFun BMI270 Arduino Library（IMU）

### 5.4 ピン仕様（v1.2実装）
`include/board_atoms3r_m12_pins.h` に定義される。  
- カメラ（OV3660）: CAM_SDA/CAM_SCL、VSYNC/HREF/PCLK、Y2..Y9、XCLK、PWDN  
- IMU（BMI270）: I2Cは **SYS_SDA=GPIO45**, **SYS_SCL=GPIO0** を使用  
  - `Wire.begin(IMU_PIN_SDA, IMU_PIN_SCL)` を必ず明示する（デフォルトI2Cピンでは動かない可能性がある）

### 5.5 IMU仕様（v1.2実装）
- I2C addr: 0x68（Primary）
- フレーム送信前に `getSensorData()` を呼び、直近値を `ax..gz` として同梱する。
- IMU初期化が失敗してもストリーミング継続（IMU値なし/NaNで送信）

### 5.6 LED制御（外部照明）
- PWMで外付けLEDを制御する（治具の照明）
- PWM周波数は縞（バンディング）に影響するため `LED_PWM_FREQ_HZ` を実験で調整できるようにする

### 5.7 エラー処理（最低限）
- Wi-Fi切断時は再接続し、ストリーミングを再開する
- HTTP送信失敗時は軽いバックオフを入れる
- camera init失敗時は再起動（実装はESP.restart）

---

## 6. Collector PC 実装仕様（FastAPI + Web UI）

### 6.1 起動方法（実装に即した手順）

Collector PC は `collector/pyproject.toml` に依存関係を定義し、**uv** で環境を構築する。

```powershell
cd collector
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

UI: `http://localhost:8000/ui/`

補足:
- `uv sync` により `.venv/` と `uv.lock` が生成される（初回のみ）。
- `uv run` を使うと、仮想環境のactivate手順（PowerShell / cmd / bash差）を意識せずに起動できる。


### 6.2 config読み込み規約（実装）
Collectorは以下の順に `config.yaml` を探索し、見つからなければ `config_example.yaml` を利用する。
- `config.yaml`（カレント、親、祖父母）
- `config_example.yaml`（カレント、親、祖父母）

### 6.3 UI（v1.2で実装済みの項目）
- Preview（最新画像）
- セッション開始/停止
- イベント（goose/stim/confound/note）
- LEDスライダー + `set_led`送信
- Pilot（Calibrate / Report）
- **IMU表示**（ax/ay/az, gx/gy/gz, g_norm）
- **Quality表示**（luma_mean, blur, satW/satB, banding, motion_flag）
- **Device操作**
  - Ping
  - Start/Stop Stream
  - target_fps/jpeg_quality を指定して Apply（set_param）

### 6.4 品質メトリクスと motion_flag（実装）
- `blur_laplacian_var` と `g_norm` を用いて motion_flag を立てる（どちらかが閾値を超える/下回る）
- 閾値は `config.yaml` の `quality.blur_threshold` と `quality.imu_gnorm_threshold`

---

## 7. パイロット（FFTゲート）仕様（実装の詳細）

### 7.1 Calibrate
- UI/ APIで `pilot/calibrate` を呼ぶと、直近 `window_sec`（既定10秒）の gb_index から baseline mean/std を算出し、閾値 `mean + k*std` を決定する

### 7.2 Report（ゲート判定）
- Positive区間: `stim_on`～`stim_off`
- Baseline区間: `calib_start`～`calib_done`（最初の1区間）
- Confounds:
  - `confound_motion_start`～`confound_motion_stop`
  - `confound_light_start`～`confound_light_stop`

算出:
- AUC（pos vs baseline）
- baseline_sd / drift
- confound区間での誤検出（rising edges / min）

出力:
- `pilot/gb_index.csv`
- `pilot/pilot_report.json`
- `pilot/pilot_plot.png`

---

## 8. ツール（tools/）

### 8.1 simulate_device.py
実機がない状態で Collector の受信・保存・UI を検証する。  
- `/upload` に疑似JPEGと疑似IMUを送信する。

### 8.2 validate_session.py
- セッションフォルダの必須ファイル、行数、pilot生成有無、session_start/stopの有無などを検証する。

### 8.3 make_labels.py
- `events.csv` の `goose_on/off` を `frames.csv` の `pc_rx_ts_ms` へ展開して `labels.csv` を生成する。

---

## 9. 受入条件（Acceptance Criteria）

### 9.1 最小受入（P0）
- Collectorが起動し、`simulate_device.py` でプレビューが更新される。
- セッション開始後、frames/ と frames.csv/events.csv/quality.csv が生成される。

### 9.2 実機受入（P1）
- Atomからフレームが送信され、Collector UIに device_ip が表示される。
- UIから `Ping` / `set_led` が動作する（LEDが変化し events.csv に記録される）。
- IMUが接続されていれば、UIに g_norm が表示され、腕を動かすと変化する。

### 9.3 パイロット受入（P2）
- Calibrateでベースライン閾値が設定される。
- Reportで pilot_report.json が生成され gate.pass が判断される。

---

## 10. 次工程で必要になるファイル（計画確認）

- **ゲート判定まで（必須）**: `meta.json`, `frames.csv`, `frames/`, `events.csv`, `quality.csv`, `pilot/*`
- **学習へ進む場合**: 上記 + `labels.csv`（make_labelsで生成）
- **最終組込みへ進む場合**: 学習済みモデル、量子化モデル、推論ログ仕様

---


## Update v1.3: Auto Luma (Collector側自動輝度制御)

- Collector UIの `Auto Luma` で、ROI平均輝度を目標値に保つようLED PWMを自動調整する。
- API: `POST /lighting/auto` `{enabled: bool}`
- 調整はUDP `{"cmd":"set_led","pwm":...}` を **fire-and-forget** で送信し、受信系の遅延を最小化する。
- 変更が有効になった場合は `events.csv` に `led_pwm (note=auto_luma)` を記録する。
- UIプレビューには固定ROI枠が表示される（CSSオーバーレイ）。