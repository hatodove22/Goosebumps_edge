# テスト計画（実機検証チェックリスト）v1.0

更新日: 2026-01-22

本書は、AtomS3R-M12（OV3660 + BMI270）と Collector PC（FastAPI UI）を用いる鳥肌検出プロジェクトの**実機テスト項目**を整理したチェックリストである。  
実験担当者が漏れなく確認できることを目的とする。

---

## 1. 前提
- Collector PC が起動し、UI にアクセスできること。
- Atom が同一LANに接続できること（Wi-Fi）。
- 外部LEDがPWMで制御可能であること（必要に応じて電流制限/放熱）。

---

## 2. 接続・基本動作（最優先）

### 2.1 Wi-Fi接続
- [ ] 起動後に Serial にIPが表示される。
- [ ] RSSI が十分（目安: -70 dBm より良い）。
- [ ] 1分程度放置しても切断しない。

### 2.2 フレームアップロード
- [ ] Collector UI でプレビューが更新される（`/latest.jpg`）。
- [ ] `/session/start` 後、dataset に保存される（frames/ と frames.csv）。
- [ ] 5分間連続で保存され、欠損が極端に増えない。

### 2.3 連番と時刻
- [ ] frame_id が単調増加（再送は drop_flag=1 で許容）。
- [ ] device_ts_ms が増加する。
- [ ] pc_rx_ts_ms が増加する。

---

## 3. LED制御（手動）
- [ ] UIのPWMスライダー + `Send to device` で照明が変化する。
- [ ] events.csv に `led_pwm` が記録される（手動操作ログ）。
- [ ] 極端に明るい/暗い設定で sat_white_ratio / sat_black_ratio が反応する。

---

## 4. Auto Luma（自動輝度制御）
- [ ] UIの `Auto Luma` をONにすると照明が自動追従する。
- [ ] 追従中に events.csv へ `led_pwm`（note=auto_luma）が記録される。
- [ ] バンディングが強くならない（強い場合はPWM周波数/露出条件を見直す）。

---

## 5. IMU（BMI270）
- [ ] UIに `g_norm` と `gx/gy/gz`, `ax/ay/az` が表示される。
- [ ] 腕を動かすと g_norm が上がる。
- [ ] motion_flag が適切に上がる（閾値はconfigで調整）。

---

## 6. 品質メトリクス
- [ ] luma_mean が輝度変化に追従する。
- [ ] blur_laplacian_var がピント/ブレに反応する。
- [ ] banding_score が縞の出現に反応する（粗い検出でもOK）。

---

## 7. パイロット（FFTゲート）

### 7.1 Calibrate
- [ ] Calibrate（10秒）で baseline（mean/std/thr）が表示される。
- [ ] events.csv に calib_start/calb_done が記録される（窓時刻が一致）。

### 7.2 Positive / Negative / Confound
- [ ] stim_on/off を記録できる。
- [ ] goose_on/off を記録できる（必要なら reaction delay を使用）。
- [ ] confound_motion/light 区間を記録できる。

### 7.3 Report
- [ ] pilot_report.json / pilot_plot.png / gb_index.csv が生成される。
- [ ] gate.pass が期待通り（failなら観測系を改善）。

---

## 8. ストレス・耐障害
- [ ] Wi-Fiを一時遮断しても復帰する（ファーム再接続）。
- [ ] Collector を停止/再起動しても、次セッションで保存が復帰する。
- [ ] 長時間（30分）運用でメモリ/発熱によるクラッシュがない。

---

## 9. データ検証（ツール）
- [ ] `python tools/validate_session.py <session_dir>` がPASSする。
- [ ] `python tools/make_labels.py <session_dir>` で labels.csv が生成できる。

