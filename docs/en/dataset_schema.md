# Dataset Schema - Goosebumps EdgeAI (Schema v1.1)

Updated: 2026-01-15

This document defines the **session folder** structure stored by the data acquisition system (Collector) and the column definitions for each CSV/JSON.  
Compatibility with downstream steps (FFT gate, training, deployment) is prioritized, and breaking changes are avoided.

> v1.1 adds the **imu.csv** definition and clarifies implementation behavior (frames.csv drop_flag, empty filename).

---

## 1. Directory Structure (per session)
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
      labels.csv   (optional)
```

---

## 2. meta.json (Required)

### 2.1 Purpose
- Fix session conditions, mounting, lighting, and software versions to ensure reproducibility.

### 2.2 Required Keys (Minimum)
- `schema_version`
- `subject_id`
- `session_id`
- `created_at_pc_ms`
- `camera`, `roi`, `lighting`, `quality`, `pilot_fft`
- `software.collector_version`

---

## 3. frames.csv (Required)

### 3.1 Purpose
- Record timestamp and filename mapping for received frames.

### 3.2 Column Definitions
|Column|Type|Description|
|---|---|---|
|frame_id|int|Sequential ID (device-side)|
|device_ts_ms|int|Device relative timestamp|
|pc_rx_ts_ms|int|PC receive timestamp|
|filename|string|`frames/000123.jpg` (empty if dropped)|
|width|int|Image width|
|height|int|Image height|
|jpeg_bytes|int|JPEG size|
|drop_flag|int|1 indicates duplicate/retransmit (do not save)|

**Operational Rule**
- Exclude rows with `drop_flag=1` in analysis (filename may be empty).

---

## 4. imu.csv (Optional but Recommended; output in v1.2)

### 4.1 Purpose
- Record motion at frame time to help exclude blur/motion segments (motion_flag).

### 4.2 Column Definitions (Minimum)
|Column|Type|Description|
|---|---|---|
|pc_rx_ts_ms|int|Frame receive timestamp|
|frame_id|int|Corresponding frame|
|ax,ay,az|float|Acceleration (unit per implementation/library)|
|gx,gy,gz|float|Angular velocity (unit per implementation/library)|
|g_norm|float|`sqrt(gx^2+gy^2+gz^2)` (used for motion)|

---

## 5. events.csv (Required)

### 5.1 Purpose
- Save stimuli, goosebumps labels, and lighting operations as an event log, then expand into frame labels.

### 5.2 Column Definitions
|Column|Type|Description|
|---|---|---|
|pc_ts_ms|int|PC timestamp when event is recorded|
|type|string|Event type (e.g., goose_on)|
|value|string/int|Value|
|note|string|Free text|

### 5.3 Recommended Events
- `session_start`, `session_stop`
- `stim_on`, `stim_off`
- `goose_on`, `goose_off`
- `led_pwm` (PWM value in value)
- `calib_start`, `calib_done`
- `confound_motion_start/stop`, `confound_light_start/stop`
- `note`

---

## 6. quality.csv (Required)

### 6.1 Purpose
- Record per-frame quality metrics (exposure, blur, banding, motion) for exclusion and analysis.

### 6.2 Column Definitions (Minimum)
|Column|Type|Description|
|---|---|---|
|frame_id|int|Frame ID|
|pc_rx_ts_ms|int|Receive timestamp|
|luma_mean|float|ROI mean luminance|
|sat_white_ratio|float|White saturation ratio|
|sat_black_ratio|float|Black saturation ratio|
|blur_laplacian_var|float|Blur metric|
|banding_score|float|Banding score (coarse)|
|motion_flag|int|1 means large motion/blur (exclude candidate)|

---

## 7. pilot/ (Optional; FFT Gate)

### 7.1 gb_index.csv
|Column|Type|Description|
|---|---|---|
|pc_rx_ts_ms|int|Timestamp|
|gb_index|float|Raw|
|gb_smooth|float|Smoothed|
|gb_binary|int|After threshold|

### 7.2 pilot_report.json
- Includes `gate.pass` (bool) with reason, AUC, false positive rate, etc.

---

## 8. labels.csv (Optional; for training)

### 8.1 Purpose
- Teacher labels expanded from `events.csv` into per-frame labels.

### 8.2 Column Definitions (Recommended)
|Column|Type|Description|
|---|---|---|
|frame_id|int|Frame ID|
|pc_rx_ts_ms|int|Timestamp|
|filename|string|Image path|
|piloerection|int|0/1|
|use_flag|int|1 to use for training (can set to 0 for motion_flag)|
|note|string|Notes|

---

## 9. Schema Change Rules (Short)
- Breaking changes require a `schema_version` bump.
- Additive columns are allowed (backward compatible).
- Changing existing semantics is prohibited (add new fields instead).

---
