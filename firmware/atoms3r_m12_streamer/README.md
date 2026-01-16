# AtomS3R-M12 Streamer (PlatformIO)

Firmware for **M5Stack AtomS3R-M12 (OV3660 M12 camera)**:
- Captures JPEG frames from the camera
- Uploads frames to Collector PC (`POST /upload`) as `multipart/form-data`
- Listens for UDP JSON commands (LED PWM, start/stop streaming, ping, set_param)
- Reads the on-board **BMI270 IMU** (optional) and attaches `ax,ay,az,gx,gy,gz,g_norm` to each upload

## AtomS3R-CAM (GC0308, non-M12) support
This firmware also works on **AtomS3R-CAM (GC0308)** (non-M12).

- `CAMERA_VARIANT`: `0` = GC0308 (non-M12), `1` = M12 (OV3660)
- GC0308 uses **RGB565 -> software JPEG**, so FPS will be lower
- Required settings for GC0308:
  - POWER_N (GPIO18) must be driven **LOW** before init
  - `pin_pwdn = -1`
  - `xclk_freq_hz = 20000000`
  - `sccb_i2c_port = 1`
  - Init order: **Camera -> IMU**
## 1) Configure
Edit `include/user_config.h`:
- `WIFI_SSID`, `WIFI_PASS`
- `COLLECTOR_HOST` (Collector PC IP), `COLLECTOR_PORT` (default 8000)
- `LED_PWM_PIN` (your external LED pin), `LED_PWM_FREQ_HZ`

## 2) Build & Upload (PlatformIO)
From this folder:
```bash
pio run -t upload
pio device monitor
```

## 3) Runtime control (UDP JSON)
Device listens on `UDP_CMD_PORT` (default 3333).

Examples:
```json
{"cmd":"ping"}
{"cmd":"set_led","pwm":128}
{"cmd":"start_stream"}
{"cmd":"stop_stream"}
{"cmd":"set_param","jpeg_quality":20,"target_fps":12}
{"cmd":"reboot"}
```

Collector PC will automatically send `set_led` via its `/device/cmd` API after it learns the device IP (once the device uploads at least one frame).

## Notes
- If you see `PSRAM not found`, ensure `platformio.ini` has `board_build.arduino.memory_type = qio_opi`.
- Banding (flicker stripes) may depend on PWM frequency and camera exposure; try different `LED_PWM_FREQ_HZ`.

### IMU (BMI270) fields
When the BMI270 is detected, the firmware appends the following form fields to `POST /upload`:
- `ax, ay, az`: accelerometer in **g**
- `gx, gy, gz`: gyroscope in **deg/s**
- `g_norm`: `sqrt(gx^2 + gy^2 + gz^2)` (deg/s)

The BMI270 I2C pins on AtomS3R-M12 are `SYS_SDA=GPIO45`, `SYS_SCL=GPIO0` (see M5Stack PinMap).
- IMU: on AtomS3R-M12, BMI270 is at I2C address `0x68` on `SYS_SDA/SYS_SCL` (GPIO45/GPIO0). If the IMU init fails, streaming continues without IMU fields.



