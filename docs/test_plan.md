# Test Plan (実機テスト項目まとめ) v1.0

本書は、AtomS3R-M12（OV3660 + BMI270）とCollector PC（FastAPI UI）を用いた鳥肌検出プロジェクトの **実機テスト項目**を、実験担当者が漏れなく確認できるように整理したものです。

## 1. 前提
- Collector PCが起動し、UIへアクセスできる
- Atomが同一LANに接続できる（Wi-Fi）
- 外部LEDがPWMで制御可能（必要に応じて電流制限・放熱）

## 2. 接続・基本動作（最優先）
### 2.1 Wi-Fi接続
- [ ] 起動後にSerialへIPが表示される
- [ ] RSSIが十分（目安：-70dBmより良い）
- [ ] 1分放置しても切断しない

### 2.2 フレームアップロード
- [ ] Collector UIでプレビューが更新される（/latest.jpg）
- [ ] `/session/start`後、datasetに保存される（frames/ と frames.csv）
- [ ] 5分連続で保存が継続し、欠損が極端に増えない

### 2.3 連番と時刻
- [ ] frame_idが単調増加（再送時はdrop_flag=1で許容）
- [ ] device_ts_msが増加
- [ ] pc_rx_ts_msが増加

## 3. LED制御（手動）
- [ ] UIのPWMスライダー → `Send to device`で照明が変化する
- [ ] events.csvに `led_pwm` が記録される（手動操作ログ）
- [ ] 極端に明るく/暗くしたとき、sat_white_ratio / sat_black_ratio が反応する

## 4. Auto Luma（自動輝度制御）
- [ ] UIの `Auto Luma` をONにすると、照明が自動で追従する
- [ ] 追従中、events.csvに `led_pwm`（note=auto_luma）が記録される
- [ ] banding（縞）が強くならない（強くなる場合はPWM周波数・露出条件を再検討）

## 5. IMU（BMI270）
- [ ] UIに `g_norm` と `gx/gy/gz`、`ax/ay/az` が表示される
- [ ] 腕を動かすと g_norm が上がる（直観的に変化）
- [ ] motion_flag が適切に上がる（閾値はconfigで調整）

## 6. 品質メトリクス
- [ ] luma_mean が輝度変化に追従
- [ ] blur_laplacian_var がピント/ブレに反応
- [ ] banding_score が縞の出現に反応（厳密でなくても「兆候」が出る）

## 7. パイロット（FFTゲート）
### 7.1 Calibrate
- [ ] Calibrate（10秒）でbaselineが表示される（mean/std/thr）
- [ ] events.csvに calib_start/calb_done が記録される（窓時刻が一致）

### 7.2 Positive/Negative/Confound
- [ ] stim_on/off を記録できる
- [ ] goose_on/off を記録できる（必要ならreaction delay使用）
- [ ] confound_motion/light 区間を記録できる

### 7.3 Report
- [ ] pilot_report.json / pilot_plot.png / gb_index.csv が生成される
- [ ] gate.pass の判定が期待通り（failなら観測系改善へ）

## 8. ストレス・耐障害
- [ ] Wi-Fiを一時的に遮断しても復帰する（ファーム側再接続）
- [ ] Collectorが一時停止/再起動しても、次セッションで保存が復帰する
- [ ] 長時間（30分）運用してもメモリ/発熱で落ちない

## 9. データ検証（ツール）
- [ ] `python tools/validate_session.py <session_dir>` がPASSする
- [ ] `python tools/make_labels.py <session_dir>` で labels.csv が生成できる
