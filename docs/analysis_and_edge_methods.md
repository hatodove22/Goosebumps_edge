# ロギング・解析・エッジ推論の実装ガイド（v1）

更新日: 2026-01-16

本書は、鳥肌（piloerection）検出プロジェクトにおいて、

- **収集データ（ロギング）から解析・学習に必要な情報**を整理し、
- **スクリプト群（tools/）で再現可能な解析・学習フロー**を定義し、
- **エッジ処理に適した推論方式**を2案（簡易案 / 高性能案）として提示し、実装手順をまとめる。

対象読者は「目的は共有済みだが初見の実装担当者」であり、迷わず進められる手順と入出力ファイルを明確にする。

---

## 0. 結論（最初に選ぶべきプラン）

### プランA（簡単かつ確実）: テクスチャ指数 + 閾値（セッション内キャリブレーション）
- 特徴量: **Laplacian強度（lap_abs_mean / lap_var）** などの軽量テクスチャ指数
- 判定: ベースライン（キャリブレーション区間）で平均・分散を取り、`mean + k*std` を閾値にして検出
- 追加: IMU・ブレ・飽和などの**品質ゲート**で誤検出を下げる

利点:
- 学習不要（GIGOリスクが最小）
- 実装が単純で、ESP32-S3上で実装しやすい
- ラベル作業が少なくても運用開始できる

欠点:
- 個人差・照明差・毛量差に弱い可能性がある（調整が必要）

### プランB（より効果的）: LBPヒストグラム + 線形分類器（ロジスティック回帰）
- 特徴量: **LBP（Local Binary Pattern）256-binヒストグラム**
- 学習: `tools/train_lbp_lr.py`（numpyのみ）で学習し、モデルをJSONとして保存
- 組込み: `tools/export_lbp_lr_header.py` でCヘッダへ変換し、ファームに組み込む

利点:
- プランAより条件変動（照明・個人差）に強くなりやすい
- 推論コストは低い（LBP + dot product）

欠点:
- ラベル付きデータが必要（ただし深層学習よりは少量でも成立しやすい）

---

## 1. ロギングで必須/推奨となる情報

本プロジェクトは「データ収集 → 品質確認 → 特徴量確認（GIGO回避） → 学習 → 組込み」を繰り返す。
このため、**後から再現できるログ**が重要である。

### 1.1 必須（Collectorが生成）
セッションディレクトリ（例: `dataset/subject_001/2026-01-16_session_01/`）に以下が必要。

- `meta.json`（条件固定）
  - ROIサイズ、照明設定（PWM範囲、auto_lumaなど）、品質閾値、FFT設定など
- `frames/` + `frames.csv`
  - フレームID、PC受信時刻、JPEGパス
- `quality.csv`
  - ROI平均輝度、飽和率、ブレ指標、縞指標、motion_flag
- `events.csv`
  - 刺激・鳥肌ラベル・照明操作・メモ等
- （推奨）`imu.csv`
  - frame_idと対応するIMU値（g_norm）

### 1.2 学習に必須（後処理で生成）
- `labels.csv`
  - `events.csv` の `goose_on/off` をフレームへ展開した教師ラベル
  - 生成: `tools/make_labels.py`

### 1.3 推奨イベント（events.csv）
最低限これだけ入ると後工程が成立する。

- `calib_start` / `calib_done`
  - ベースライン区間（鳥肌なし）を明示
- `stim_on` / `stim_off`
  - 刺激区間（刺激がある＝鳥肌の可能性が高い）
- `goose_on` / `goose_off`
  - オペレータ判断の鳥肌ラベル（教師信号）
- `led_pwm`（valueにPWM値、noteにmanual/autoなど）
- `confound_motion_start/stop`（固定具調整など）
- `confound_light_start/stop`（遮光が崩れた等）
- `note`（備考を残す）

---

## 2. 解析フロー（ファイルがいつ必要か）

### 2.1 セッション収集直後
1) `tools/validate_session.py` で最低限の整合性確認
2) UIで `pilot/report` を実行し、FFTゲートで「特徴が見えているか」を確認（GIGO回避）

### 2.2 ラベル生成
- `events.csv` に `goose_on/off` が入ったら、`tools/make_labels.py` で `labels.csv` を生成

### 2.3 特徴量導出（GIGO回避のための最低ステップ）
- `tools/derive_features.py` で、
  - FFTテクスチャ指数（gb_fft_index）
  - Laplacian系テクスチャ指数（lap_abs_mean）
  を導出し、**AUCや平均差**を確認する。

### 2.4 学習（プランB）
- `tools/train_lbp_lr.py` で LBP+LR を学習（モデルJSON生成）
- `tools/infer_lbp_lr.py` でセッション単位の推論確認
- `tools/export_lbp_lr_header.py` でファーム用ヘッダ生成

---

## 3. 付属スクリプト（tools/）と入出力

### 3.1 セッション整合性チェック
- `tools/validate_session.py <session_dir>`

### 3.2 ラベル生成（events → labels）
- `tools/make_labels.py <session_dir>`

生成物:
- `<session_dir>/labels.csv`

### 3.3 特徴量導出（FFT / Laplacian）
- `tools/derive_features.py <session_dir>`

生成物:
- `<session_dir>/derived/features.csv`
- `<session_dir>/derived/features_report.json`
- `<session_dir>/derived/features_plot.png`（matplotlibがある場合）

Windows（uv）例:
```powershell
cd collector
uv run python ../tools/derive_features.py ../dataset/subject_001/2026-01-16_session_01
```

### 3.4 学習（LBP + Logistic Regression）
- `tools/train_lbp_lr.py --dataset-root <dataset_root> --out <model.json>`

生成物:
- `<repo_root>/models/lbp_lr_model.json`

Windows（uv）例:
```powershell
cd collector
uv run python ../tools/train_lbp_lr.py --dataset-root ../dataset --out ../models/lbp_lr_model.json --require-motion-ok
```

### 3.5 推論（LBP + LR）
- `tools/infer_lbp_lr.py --model <model.json> <session_dir>`

生成物:
- `<session_dir>/derived/pred_lbp_lr.csv`
- `<session_dir>/derived/pred_lbp_lr_report.json`

### 3.6 ファーム用ヘッダの生成
- `tools/export_lbp_lr_header.py --model <model.json> --out <header.h>`

例:
```powershell
cd collector
uv run python ../tools/export_lbp_lr_header.py --model ../models/lbp_lr_model.json --out ../firmware/atoms3r_m12_streamer/include/model_lbp_lr.h
```

---

## 4. プランA（簡単かつ確実）実装手順

### 4.1 目的
- 学習無しで「鳥肌が立った可能性が高い区間」を検出し、
  - 記録（ログ）
  - 刺激条件の有効性確認
  - 後の学習用ラベル付け支援
  に活用する。

### 4.2 アルゴリズム（推奨）
1) ROI取得（固定中心ROI）
2) テクスチャ指数 `T` を計算（例: `lap_abs_mean`）
3) キャリブレーション区間（`calib_start..calib_done`）で `mean/std` を計算
4) 閾値 `thr = mean + k*std`（k=3程度）
5) `T > thr` を一定時間（例: 0.5s）継続したら鳥肌ON
6) ヒステリシス（例: OFFは `mean + 2*std`）や移動平均を入れてチャタリング防止
7) motion_flag=1 等の品質不良は判定を保留（直近状態維持）

### 4.3 実装先
- 最短: **Collector側（既にFFT指数は計算済み）**
- 次: **ESP32-S3側**へ移植（laplacianは軽量で移植しやすい）

### 4.4 ロギング（推奨）
- 推論結果（ON/OFF）を `events.csv` に追記（例: `gb_pred_on/off`）
- 閾値とキャリブレーション統計を `meta.json` に追記して再現性を確保

---

## 5. プランB（より効果的）実装手順（LBP+LR）

### 5.1 データ準備
1) セッション収集（固定具・遮光・LED制御）
2) `events.csv` に `goose_on/off` を記録
3) `tools/make_labels.py` で `labels.csv` を生成
4) `tools/derive_features.py` で特徴量の見えを確認（AUCが極端に低い場合は設計を見直す）

### 5.2 学習
- `tools/train_lbp_lr.py` を実行し `models/lbp_lr_model.json` を生成
- 可能なら session split で val AUC を確認

### 5.3 組込み
- `tools/export_lbp_lr_header.py` で `model_lbp_lr.h` を生成
- ファーム側で以下を実装
  - ROIを `input_size`（例: 64）にリサイズ
  - LBPヒストグラム（256 bin）を計算
  - `p = sigmoid(dot(w, hist) + b)`
  - `p >= threshold` で検出

### 5.4 実機確認
- Collectorへ推論結果を送る（HTTP formに `gb_prob` などを追加するか、UDPイベント送信）
- まずは「推論値の時系列が素直に変動しているか」を見る

---

## 6. より先の高性能化（将来計画）

深層学習（Tiny CNN）へ進む場合は、LBP+LRで
- ROIサイズ
- 照明条件
- ラベル品質
- 品質ゲート
を固めてから移行する。

Tiny CNNの基本方針（参考）:
- 入力: 96x96 grayscale
- モデル: depthwise separable conv を数段
- 量子化: int8
- 実行: TensorFlow Lite Micro

---

## 7. トラブルシューティング（解析・学習）

- 学習AUCが0.5付近で改善しない
  - ROIが皮膚領域を外れていないか
  - 遮光が崩れて照明が変動していないか
  - motion_flagが高い（固定具が甘い）
  - goose_on/off が刺激の有無を表しているだけになっていないか（真の鳥肌を見ているか）

- 推論がONしっぱなし
  - キャリブレーション区間に鳥肌が混じっていないか
  - LEDが飽和していないか（sat_white_ratio）

---

