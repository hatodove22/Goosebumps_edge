# ロギング・解析・エッジ推論 実装ガイド（v1）

更新日: 2026-01-22

本書は、鳥肌（立毛）検出プロジェクトにおける以下を**最短で再現できる形**に整理する。  

- 解析・学習に必要な**ロギング項目**
- `tools/` を使った**再現可能な解析/学習フロー**
- エッジ実装向けの**2つの推論プラン（簡単/高性能）**と実装ステップ

対象読者は「目的は共有済みだが初めて触れる実装者」。  
どのファイルを、いつ、どう作るかを明確にする。

---

## 0. 結論（最初にプランを選ぶ）

### プランA（簡単・堅実）: テクスチャ指標 + 閾値（セッション内キャリブレーション）
- 特徴量: **Laplacian強度（lap_abs_mean / lap_var）**などの軽量テクスチャ
- 判定: ベースライン区間で mean/std を計算し `mean + k*std` で検出
- 追加: **品質ゲート**（IMU/ブレ/飽和）で誤検出低減

メリット:
- 学習不要（GIGOリスク最小）
- ESP32-S3でも実装しやすい
- ラベルが少なくても運用開始できる

デメリット:
- 個人差/照明差に弱い（調整が必要）

### プランB（高性能）: LBPヒストグラム + 線形分類器（ロジスティック回帰）
- 特徴量: **LBP（Local Binary Pattern）256-bin**
- 学習: `tools/train_lbp_lr.py` でモデルJSONを生成
- 組込み: `tools/export_lbp_lr_header.py` でCヘッダ化

メリット:
- プランAより条件変動に強い
- 推論コストが低い（LBP + dot）

デメリット:
- ラベル付きデータが必要（ただし深層学習ほど多くは不要）

---

## 1. ロギング：必要な情報

本プロジェクトは「収集 → 品質確認 → 特徴量確認（GIGO回避） → 学習/組込み」を繰り返す。  
後から再現できるログが必須。

### 1.1 必須（Collectorが生成）
セッションディレクトリ（例: `dataset/subject_001/2026-01-16_session_01/`）に以下があること。

- `meta.json`（条件固定）
  - ROI、照明設定（PWM、auto_luma）、品質閾値、FFT設定など
- `frames/` + `frames.csv`
  - frame_id、受信時刻、JPEGパス
- `quality.csv`
  - ROI平均輝度、飽和率、ブレ、縞、motion_flag
- `events.csv`
  - 刺激・鳥肌ラベル・照明操作・メモ
- （推奨）`imu.csv`
  - IMU値（g_norm 等）を frame_id と対応付け

### 1.2 学習に必須（後処理で生成）
- `labels.csv`
  - `events.csv` の goose_on/off をフレームへ展開した教師ラベル
  - 生成: `tools/make_labels.py`

### 1.3 推奨イベント（events.csv）
最低限これがあればパイプラインが成立する。

- `calib_start` / `calib_done`（ベースライン区間）
- `stim_on` / `stim_off`（刺激区間）
- `goose_on` / `goose_off`（手動ラベル）
- `led_pwm`（valueにPWM値、noteにmanual/auto等）
- `confound_motion_start/stop`
- `confound_light_start/stop`
- `note`（自由記述）

---

## 2. 解析フロー（いつ何が必要か）

### 2.1 収集直後
1) `tools/validate_session.py` で整合性チェック  
2) UIの `pilot/report` で FFTゲート確認（GIGO回避）

### 2.2 ラベル生成
`events.csv` に `goose_on/off` がある場合、`tools/make_labels.py` で `labels.csv` を生成。

### 2.3 特徴量導出（GIGO回避の最小ステップ）
`tools/derive_features.py` で以下を算出し、**AUCと平均差**を確認する。
- FFT指標: `gb_fft_index`
- Laplacian指標: `lap_abs_mean`

### 2.4 学習（プランB）
`tools/train_lbp_lr.py` で学習し、`tools/infer_lbp_lr.py` で検証し、`tools/export_lbp_lr_header.py` でファーム用ヘッダ化。

---

## 3. ツール（tools/）と入出力

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

### 3.6 ファーム用ヘッダ生成
- `tools/export_lbp_lr_header.py --model <model.json> --out <header.h>`

例:
```powershell
cd collector
uv run python ../tools/export_lbp_lr_header.py --model ../models/lbp_lr_model.json --out ../firmware/atoms3r_m12_streamer/include/model_lbp_lr.h
```

---

## 4. プランA（簡単・堅実）実装ステップ

### 4.1 目的
学習なしで「鳥肌が立った可能性が高い区間」を検出し、  
ログ/刺激の有効性確認/今後のラベル作業支援に使う。

### 4.2 推奨アルゴリズム
1) 固定ROIを取得  
2) テクスチャ指標 `T` を計算（例: `lap_abs_mean`）  
3) `calib_start..calib_done` 区間で `mean/std` を算出  
4) `thr = mean + k*std`（k=3が目安）  
5) `T > thr` が一定時間（例: 0.5s）継続したらON  
6) OFFは `mean + 2*std` などヒステリシス or 移動平均でチャタリング防止  
7) motion_flag=1 など品質不良時は判定保留（直近状態維持）

### 4.3 実装ターゲット
- 最短: **Collector側**（FFT指標が既に計算済み）
- 次: **ESP32-S3側**（Laplacianは軽量）

### 4.4 ロギング推奨
- 推論ON/OFFを `events.csv` に記録（例: `gb_pred_on/off`）
- 閾値とキャリブレーション統計を `meta.json` に保存

---

## 5. プランB（高性能）実装ステップ（LBP+LR）

### 5.1 データ準備
1) セッション収集（治具/遮光/LED制御）  
2) `events.csv` に `goose_on/off` を記録  
3) `tools/make_labels.py` で `labels.csv` 生成  
4) `tools/derive_features.py` で特徴の見えを確認（AUCが低ければ設計見直し）

### 5.2 学習
- `tools/train_lbp_lr.py` で `models/lbp_lr_model.json` を生成
- 可能ならセッション分割でAUC検証

### 5.3 組込み
- `tools/export_lbp_lr_header.py` で `model_lbp_lr.h` を生成
- ファーム側で以下を実装:
  - ROIを `input_size`（例: 64）へリサイズ
  - LBPヒストグラム（256 bin）計算
  - `p = sigmoid(dot(w, hist) + b)`
  - `p >= threshold` で検出

### 5.4 実機確認
- 推論結果をCollectorへ送る（HTTP formに `gb_prob` 等を追加 or UDPイベント）
- 時系列の挙動が素直に変動するかを見る

---

## 6. 高性能化（将来）

深層学習（Tiny CNN）へ進む場合、先に以下を安定化させる。
- ROIサイズ
- 照明条件
- ラベル品質
- 品質ゲート

Tiny CNNの目安（参考）:
- 入力: 96x96 grayscale
- モデル: depthwise separable conv を数段
- 量子化: int8
- ランタイム: TensorFlow Lite Micro

---

## 7. トラブルシューティング（解析・学習）

- 学習AUCが0.5付近から上がらない:
  - ROIが皮膚を外れている
  - 遮光が崩れて照明変動が大きい
  - motion_flagが高い（治具が緩い）
  - goose_on/off が刺激の有無だけを表している（真の鳥肌ではない）

- 推論がONしっぱなし:
  - キャリブレーション区間に鳥肌が混じっている
  - LEDが飽和している（sat_white_ratio）

