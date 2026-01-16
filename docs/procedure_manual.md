# 鳥肌（立毛）検出エッジAIシステム — 手順書（Procedure Manual） v1.4

更新日: 2026-01-16

本書は、初見の実装担当者・実験担当者が **同一の手順で再現性あるデータ取得**と **事前検証（FFTゲート）**を実施できるように、準備から運用、判定、データ引き渡しまでを手順化したものである。  
本書の前提として、読者は研究目的（鳥肌検出の実現）を共有済みである。

> v1.4 では、Windows（PowerShell）でのセットアップ手順と、uv を使った依存関係管理（uv sync / uv run）に対応した。

関連: `docs/implementation_spec.md`

---

## 1. 役割分担（推奨）
- **実装担当（Developer）**
  - Collector PC（受信・UI・保存・パイロット）セットアップ
  - Atomファーム（PlatformIO）ビルド・書き込み
  - トラブル対応（ネットワーク、依存、I2C等）
- **実験担当（Operator）**
  - 被験者への装着（治具、遮光）
  - LED調整、ラベリング操作（goose/stim/confound）
  - セッションメタ情報の記録
- **解析担当（Analyst）**
  - gate pass セッション選別、labels.csv生成、解析

---

## 2. 初回セットアップ（Collector PC）

Collector PC（FastAPI UI）は **uv** を使って依存関係と仮想環境（`.venv/`）を管理する。

### 2.0 前提
- OS: Windows 10/11（PowerShell推奨）または macOS/Linux
- ネットワーク: AtomとCollector PCが同一LANに接続できる
- 既定ポート: `8000`（変更する場合は起動コマンドとファーム設定を一致させる）

### 2.1 uv のインストール（Windows推奨手順）
**Windows (PowerShell)**

```powershell
# 推奨: WinGet
winget install --id=astral-sh.uv -e

# 代替: 公式インストーラ（PowerShellスクリプト）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

> `uv --version` でインストール確認を行う。

**macOS / Linux（参考）**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2.2 依存関係インストール（.venv 作成）
```powershell
cd collector
uv sync
```

- 初回は `collector/.venv/` と `collector/uv.lock` が生成される。
- Pythonが未インストールの場合でも、uvは必要に応じてPythonを自動的に用意できる（ネットワークが必要）。  
  手動で明示する場合は `uv python install 3.11` などを利用する。

### 2.3 起動（uv run 推奨）
```powershell
cd collector
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

UI: `http://localhost:8000/ui/`

> Windowsで別PCからUIにアクセスする場合、ファイアウォールで `8000/tcp` の受信許可が必要になることがある。

### 2.4 実機なしスモークテスト（推奨）
```powershell
cd collector
uv run python ../tools/simulate_device.py --host http://127.0.0.1:8000 --fps 8 --seconds 10
```

- UIのPreviewが更新されること
- セッション開始中なら dataset/ に保存されること

---

## 3. AtomS3R-M12（PlatformIO）セットアップ

### 3.1 設定編集
`firmware/atoms3r_m12_streamer/include/user_config.h` を編集する。
- Wi-Fi SSID/PASS
- CollectorホストIP（PCのIP）
- LED PWM ピン（外付けLED用）

### 3.2 書き込み
```bash
cd firmware/atoms3r_m12_streamer
pio run -t upload
pio device monitor
```
Serialに以下が出ることを確認する。
- Wi-Fi接続成功とIP表示
- Camera init OK
- IMU init OK（接続されていれば）

---

## 4. 実験前準備（毎回）

### 4.1 物理装着
1. 治具でカメラ位置（距離/回転）を固定する
2. 黒布で遮光する（視野外も覆う）
3. ケーブルを固定し張力が治具に伝わらないようにする
4. LEDが目に入らない向きにする

### 4.2 Collector UI準備
1. UIを開く（/ui/）
2. Previewで皮膚がROI中心に入っていることを確認する
3. まだ device_ip が表示されない場合は、Atomが /upload を送っていない可能性がある

---

## 5. Device操作（v1.2 UI対応）

### 5.1 Ping（疎通）
- Atomが少なくとも1枚アップロードすると、UIに device_ip が表示される。
- `Ping` ボタンで応答が返ることを確認する。

### 5.2 Start/Stop Stream
- 実験開始前に `Stop Stream` で止め、準備が整ったら `Start Stream` で開始、という運用も可能。

### 5.3 パラメータ調整（Wi-Fiが不安定なとき）
- `jpeg_quality` を上げる（=圧縮を強くする）と通信量が減る
- `target_fps` を下げると欠損が減る
- UIの `Apply Params` で `set_param` を送信する

---

## 6. 照明調整（LED）

### 6.1 手動調整
- LEDスライダーで明るさを調整する。
- Quality表示を見て、白飛び（satW）と黒潰れ（satB）が小さくなる領域を選ぶ。
- 縞（banding）が大きい場合はPWM周波数の変更も検討する（ファーム設定）。

---

## 7. 事前検証（FFTゲート）プロトコル（必須）

目的：**大量ラベリング・学習の前に、観測系で鳥肌特徴が分離可能か判断する。**

### 7.1 区間構成（3本立て）
- Negative（安静）
- Positive（確実に出す。寒冷刺激等、安全優先）
- Confound（動き/照明変動）

### 7.2 実行手順
#### Step A: セッション開始
- UIで subject/operator 等を入力し `Start`

#### Step B: Baseline（Calibrate）
- 安静にして `Calibrate (10s)`
- baselineとthresholdが表示される

#### Step C: Positive
- 刺激開始で `Stim ON`（S）
- 鳥肌が出たと判断したら `Goose ON`（G）、収束で `Goose OFF`
- 刺激終了で `Stim OFF`

#### Step D: Confound
- `Confound Motion`（M）で軽く動かす
- `Confound Light`（L）でLEDを大きく変える（短時間）

#### Step E: Report
- `Generate Report` を押す
- `pilot_report.json` の gate.pass を確認する

---

## 8. IMU確認（v1.2追加）

### 8.1 UIでの確認
- IMU欄に `g_norm` が数値で表示されること（`-`やNaNでない）
- 腕を動かすと g_norm が変化し、motionがYESになりやすい

### 8.2 IMUが表示されない場合
- ファームのSerialで `[IMU] BMI270 connected` が出ているか確認
- I2Cピンが正しいか確認（SYS_SDA=GPIO45, SYS_SCL=GPIO0）
- 配線・接触不良、I2C pull-up、電源を確認

---

## 9. セッション終了後の確認とバックアップ

### 9.1 セッション検証（推奨）
```bash
python tools/validate_session.py dataset/subject_001/2026-01-15_session_01
```
- 必須ファイルの存在
- frames枚数とCSVの整合
- pilot生成有無
- session_start/stop の有無

### 9.2 バックアップ
- 収集直後に `dataset/subject_xxx/` を別媒体へコピーする。

---

## 10. 解析担当への引き渡し

### 10.1 labels.csv生成
```bash
python tools/make_labels.py dataset/subject_001/2026-01-15_session_01
```
- `events.csv` の goose_on/off をフレームへ展開して labels.csv を作る。

### 10.2 引き渡し最小セット
- `meta.json`
- `frames/` + `frames.csv`
- `quality.csv`
- `events.csv`
- `pilot/`（pilot_report.json含む）
- `labels.csv`（学習するなら）

---


## Update v1.3: Auto Luma と ROI枠表示

- Lightingパネルの `Auto Luma` をONにすると、照明PWMが自動で調整される。
- 追従中のPWMは events.csv に `led_pwm (note=auto_luma)` として記録される。
- Previewには固定ROI枠が表示される。ROI枠から皮膚が外れないように治具を調整する。
- 実機テスト項目は `docs/test_plan.md` を参照。