# Open Source Release Guide - Goosebumps EdgeAI v1.2

Updated: 2026-01-16

This document summarizes a checklist and recommended structure for releasing this project as open source in a way that is **reproducible** and **hard to misuse**.

> v1.2 reflects the migration of Collector PC dependency management to uv (pyproject.toml / uv.lock).

---

## 1. Basic Policy for Public Release (Important)
- **Do not publish skin video data that could identify individuals.**
- If you publish data, document ethics review, consent, withdrawal, and anonymization, and prioritize data contributors' rights.
- Split public artifacts into "code", "rig/circuit information", "data schema", and "sample (non-personal) data".

---

## 2. Minimum Required Files (Must Have)
- `README.md` (quickstart, requirements, experimental assumptions, cautions)
- `LICENSE`
- `collector/pyproject.toml` (Collector PC dependencies)
- `collector/uv.lock` (recommended: lock for reproducibility)
- `CITATION.cff` (if there is a paper/preprint)
- `docs/implementation_spec.md`
- `docs/procedure_manual.md`
- `docs/dataset_schema.md`
- `docs/open_source_release_guide.md`
- `collector/` (PC side)
- `firmware/atoms3r_m12_streamer/` (device side PlatformIO)
- `tools/` (simulate/validate/make_labels)

---

## 3. Required README Contents (At Release)
### 3.1 Five-Minute Runbook
- Start Collector (venv + uvicorn)
- Run `tools/simulate_device.py` for no-device validation
- Flash Atom firmware (PlatformIO) and edit user_config.h

### 3.2 Network Requirements
- Device must send /upload at least once before Collector knows device IP (/device/cmd depends on it)
- Port list (HTTP 8000, UDP 3333)

### 3.3 Hardware Requirements
- 3D-printed rig assumptions (fixed distance, light blocking)
- External LED PWM control (banding precautions)
- IMU (BMI270) I2C pins (SYS_SDA=GPIO45 / SYS_SCL=GPIO0)

---

## 4. Recommended Repository Structure (Clarity First)
```
repo/
  collector/                 # PC receiver + UI + pilot gate
  firmware/
    atoms3r_m12_streamer/    # PlatformIO project (OV3660 + BMI270 + UDP control)
  tools/                     # simulator / validators / converters
  docs/                      # specs, manuals, schema
  hardware/                  # (recommended) STL/STEP, wiring diagram, BOM
  examples/                  # sample_session (non-identifiable)
  .github/                   # issue/pr templates, CI
  LICENSE
  CITATION.cff
  README.md
```

---

## 5. Ensuring Reproducibility
### 5.1 Sample Session
- Add **small non-personal data** under `examples/sample_session/` (e.g., 50 frames from simulate).
- Ensure `pilot/report` works on the sample (CI verification is ideal).

### 5.2 Version Pinning
- Save `collector_version`, `firmware_version`, and `schema_version` and map them with tags.

---

## 6. Pre-Release Checklist
- [ ] No sensitive information such as Wi-Fi passwords (user_config.h should be example-only)
- [ ] Include `config_example.yaml`; recommend gitignore for config.yaml
- [ ] Dependencies are complete (collector/pyproject.toml, uv.lock recommended, platformio.ini)
- [ ] Procedures work end-to-end (simulate -> save -> pilot report)
- [ ] License and citation info are present
- [ ] Ethics and data publication policy are documented (if publishing)

---
