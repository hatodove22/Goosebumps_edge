# オープンソース公開ガイド - Goosebumps EdgeAI v1.2

更新日: 2026-01-22

本書は、本プロジェクトをオープンソース化する際に、**再現可能**かつ**誤用しにくい**形で公開するためのチェックリストと推奨構成をまとめる。

> v1.2 では、Collector PC の依存関係管理を uv（pyproject.toml / uv.lock）へ移行した点を反映。

---

## 1. 公開方針（最重要）
- **個人が特定され得る皮膚動画データは原則公開しない。**
- 公開する場合は、倫理審査・同意・撤回手続き・匿名化の方針を明文化し、提供者の権利を最優先する。
- 公開物は「コード」「治具/回路情報」「データ仕様」「サンプル（非個人）データ」に分割する。

---

## 2. 最低限含めるべきファイル（必須）
- `README.md`（Quickstart、要件、実験前提、注意点）
- `LICENSE`
- `collector/pyproject.toml`（Collector依存関係）
- `collector/uv.lock`（推奨: 依存固定で再現性向上）
- `CITATION.cff`（論文/プレプリントがある場合）
- `docs/implementation_spec.md`
- `docs/procedure_manual.md`
- `docs/dataset_schema.md`
- `docs/open_source_release_guide.md`
- `collector/`（PC側）
- `firmware/atoms3r_m12_streamer/`（Device側: PlatformIO）
- `tools/`（simulate/validate/make_labels）

**任意（含める場合）**
- `goosebumps_hub/`（Viewer/Control/OSC）
- `firmware/atoms3r_cam_realtime_infer/`（オンデバイス推論）

---

## 3. READMEに書くこと（公開時）

### 3.1 5分で動かす手順
- Collector起動（uv sync / uv run）
- `tools/simulate_device.py` で実機なし動作確認
- Atomファームのビルド/書き込み（PlatformIO）と user_config.h 編集

### 3.2 ネットワーク要件
- Device は `/upload` を1回送って初めて Collector がIPを把握できる（/device/cmd の前提）
- ポート一覧（HTTP 8000、UDP 3333）

### 3.3 ハードウェア要件
- 3Dプリント治具（距離固定/遮光）
- 外部LEDのPWM制御（バンディング対策が必要）
- IMU（BMI270）I2Cピン（SYS_SDA=GPIO45 / SYS_SCL=GPIO0）

---

## 4. 推奨リポジトリ構成（分かりやすさ優先）
```
repo/
  collector/                 # PC receiver + UI + pilot gate
  firmware/
    atoms3r_m12_streamer/    # PlatformIO project (OV3660 + BMI270 + UDP control)
    atoms3r_cam_realtime_infer/ # AtomS3R-CAM on-device inference (optional)
  goosebumps_hub/            # Viewer + Control + OSC (optional)
  tools/                     # simulator / validators / converters
  docs/                      # specs, manuals, schema
  hardware/                  # (推奨) STL/STEP, wiring diagram, BOM
  examples/                  # sample_session (non-identifiable)
  .github/                   # issue/pr templates, CI
  LICENSE
  CITATION.cff
  README.md
```

---

## 5. 再現性を高める方法

### 5.1 サンプルセッション
- `examples/sample_session/` に**非個人データ**を少量含める（simulateで生成した50フレーム等）。
- `pilot/report` がサンプルでも動作することをCI等で検証できると良い。

### 5.2 バージョン固定
- `collector_version`, `firmware_version`, `schema_version` を保存し、タグと対応付ける。

---

## 6. 公開前チェックリスト
- [ ] Wi-Fiパスワード等の秘匿情報が含まれていない（user_config.hはexample化）
- [ ] `config_example.yaml` を同梱し、`config.yaml` はgitignore推奨
- [ ] 依存関係が揃っている（pyproject.toml, uv.lock, platformio.ini）
- [ ] 手順どおりに動く（simulate → 保存 → pilot report）
- [ ] LICENSE / CITATION がある
- [ ] 倫理・データ公開方針が明文化されている（公開する場合）

