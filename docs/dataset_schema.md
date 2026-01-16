# Dataset Schema — Goosebumps EdgeAI (Schema v1.1)

更新日: 2026-01-15

本書は、本プロジェクトのデータ取得システム（Collector）で保存する **セッションフォルダ**の構造と、各CSV/JSONの列定義を定める。  
本スキーマは「後工程（FFTゲート/学習/組込み）」での互換性を最優先し、破壊的変更を避ける。

> v1.1 では **imu.csv** の定義を追加し、実装の挙動（frames.csvのdrop_flag、filename空など）を明文化した。

---

## 1. ディレクトリ構造（セッション単位）
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
      labels.csv   (任意)
```

---

## 2. meta.json（必須）

### 2.1 目的
- セッション条件・装着・照明・ソフトウェアバージョンなどを固定し、再現性を担保する。

### 2.2 必須キー（最小）
- `schema_version`
- `subject_id`
- `session_id`
- `created_at_pc_ms`
- `camera`, `roi`, `lighting`, `quality`, `pilot_fft`
- `software.collector_version`

---

## 3. frames.csv（必須）

### 3.1 目的
- 受信したフレームのタイムスタンプとファイル名の対応を記録する。

### 3.2 列定義
|列|型|説明|
|---|---|---|
|frame_id|int|0から連番（device側の送信ID）|
|device_ts_ms|int|deviceの相対時刻|
|pc_rx_ts_ms|int|PCが受信した時刻|
|filename|string|`frames/000123.jpg`（drop時は空）|
|width|int|画像幅|
|height|int|画像高|
|jpeg_bytes|int|JPEGサイズ|
|drop_flag|int|1なら重複/再送等で「保存対象外」扱い|

**運用ルール**
- `drop_flag=1` の行は解析で除外する（filenameが空の場合がある）。

---

## 4. imu.csv（任意だが推奨。v1.2実装で出力）

### 4.1 目的
- フレーム時点の運動量を記録し、ブレや動きの大きい区間を除外（motion_flag）する補助とする。

### 4.2 列定義（最小）
|列|型|説明|
|---|---|---|
|pc_rx_ts_ms|int|フレーム受信時刻|
|frame_id|int|対応フレーム|
|ax,ay,az|float|加速度（単位は実装/ライブラリ既定）|
|gx,gy,gz|float|角速度（単位は実装/ライブラリ既定）|
|g_norm|float|`sqrt(gx^2+gy^2+gz^2)`（motion判定に利用）|

---

## 5. events.csv（必須）

### 5.1 目的
- 刺激区間・鳥肌ラベル・照明操作などを「イベントログ方式」で保存し、後からフレームラベルへ展開する。

### 5.2 列定義
|列|型|説明|
|---|---|---|
|pc_ts_ms|int|PCでイベントが記録された時刻|
|type|string|イベント種別（例 goose_on）|
|value|string/int|値|
|note|string|自由記述|

### 5.3 推奨イベント
- `session_start`, `session_stop`
- `stim_on`, `stim_off`
- `goose_on`, `goose_off`
- `led_pwm`（valueにPWM値）
- `calib_start`, `calib_done`
- `confound_motion_start/stop`, `confound_light_start/stop`
- `note`

---

## 6. quality.csv（必須）

### 6.1 目的
- 露出・ブレ・縞・動き等の品質をフレームごとに記録し、除外や解析に用いる。

### 6.2 列定義（最小）
|列|型|説明|
|---|---|---|
|frame_id|int|フレーム|
|pc_rx_ts_ms|int|受信時刻|
|luma_mean|float|ROI平均輝度|
|sat_white_ratio|float|白飽和率|
|sat_black_ratio|float|黒飽和率|
|blur_laplacian_var|float|ボケ指標|
|banding_score|float|縞スコア（簡易）|
|motion_flag|int|1なら動き/ブレが大きい（除外候補）|

---

## 7. pilot/（任意。FFTゲート）

### 7.1 gb_index.csv
|列|型|説明|
|---|---|---|
|pc_rx_ts_ms|int|時刻|
|gb_index|float|生|
|gb_smooth|float|平滑化後|
|gb_binary|int|閾値後|

### 7.2 pilot_report.json
- `gate.pass`（bool）と理由、AUC、偽陽性率などを含む。

---

## 8. labels.csv（任意。学習用）

### 8.1 目的
- `events.csv` をフレームへ展開した教師ラベル。

### 8.2 列定義（推奨）
|列|型|説明|
|---|---|---|
|frame_id|int|フレーム|
|pc_rx_ts_ms|int|時刻|
|filename|string|画像|
|piloerection|int|0/1|
|use_flag|int|学習に使うなら1（motion_flagで0にしても良い）|
|note|string|備考|

---

## 9. スキーマ変更ルール（短縮版）
- 破壊的変更は `schema_version` を上げる。
- 追加列は原則許容（後方互換）。
- 既存列の意味変更は禁止（別名追加で対応）。

---
