# Open Source Release Guide — Goosebumps EdgeAI v1.1

更新日: 2026-01-15

本書は、本プロジェクトをオープンソース化する際に、第三者が **再現可能**かつ **誤用しにくい**形で公開するためのチェックリストと推奨構成をまとめる。

> v1.1では、PlatformIOファーム（IMU/LED制御）とCollectorの実装に合わせて、公開物とREADME要件を具体化した。

---

## 1. 公開範囲の基本方針（重要）
- **個人が特定され得る皮膚動画データは原則公開しない。**
- 公開する場合は、倫理審査・同意・撤回手続き・匿名化の方針を明文化し、データ提供者の権利を最優先する。
- 公開物は「コード」「治具・回路情報」「データ仕様」「サンプル（非個人）データ」に分ける。

---

## 2. 最低限含めるべきファイル（必須）
- `README.md`（Quickstart、要件、実験の前提、注意点）
- `LICENSE`
- `CITATION.cff`（論文/プレプリントがある場合）
- `docs/implementation_spec.md`
- `docs/procedure_manual.md`
- `docs/dataset_schema.md`
- `docs/open_source_release_guide.md`
- `collector/`（PC側）
- `firmware/atoms3r_m12_streamer/`（Device側 PlatformIO）
- `tools/`（simulate/validate/make_labels）

---

## 3. READMEに必ず書くこと（公開時）
### 3.1 5分で動かす手順
- Collector起動（venv + uvicorn）
- `tools/simulate_device.py` で実機なし動作確認
- Atomファーム（PlatformIO）書き込み方法（user_config.hを編集）

### 3.2 ネットワーク要件
- Deviceは /upload を送って初めて CollectorがIPを把握すること（/device/cmdの前提）
- ポート一覧（HTTP 8000、UDP 3333）

### 3.3 ハードウェア要件
- 3Dプリント治具の設計前提（距離固定、遮光）
- 外部LEDのPWM制御（バンディング対策の注意）
- IMU（BMI270）I2Cピン（SYS_SDA=GPIO45 / SYS_SCL=GPIO0）

---

## 4. 推奨リポジトリ構造（分かりやすさ優先）
```
repo/
  collector/                 # PC receiver + UI + pilot gate
  firmware/
    atoms3r_m12_streamer/    # PlatformIO project (OV3660 + BMI270 + UDP control)
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

## 5. 再現性（Reproducibility）を担保する方法
### 5.1 サンプルセッション
- `examples/sample_session/` に **少量の非個人データ**（例：simulateで生成した50フレーム）を含める。
- `pilot/report` がサンプルでも動作すること（CIで検証すると良い）。

### 5.2 バージョン固定
- `collector_version`, `firmware_version`, `schema_version` を必ず保存し、タグで対応付ける。

---

## 6. 公開前チェックリスト
- [ ] Wi-Fiパスワード等の秘匿情報が含まれていない（user_config.hはexample化）
- [ ] `config_example.yaml` を同梱し、config.yamlはgitignore推奨
- [ ] 依存関係（requirements.txt, platformio.ini）が揃っている
- [ ] 手順通りに動く（simulate→保存→pilot report）
- [ ] ライセンス・引用情報がある
- [ ] 倫理・データ公開方針が明文化されている（公開するなら）

---
