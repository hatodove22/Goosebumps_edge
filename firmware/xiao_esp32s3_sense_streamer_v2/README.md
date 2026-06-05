# XIAO ESP32S3 Sense Streamer v2.0

Firmware for **Goosebumps Edge AI v2.0** hardware:

- Board: Seeed Studio XIAO ESP32S3 Sense
- Camera: OV3660 on the Sense expansion board
- Upload: JPEG frames to Collector PC via `POST /upload`
- Control: UDP JSON commands compatible with the Collector UI
- IMU: not included in the standard XIAO ESP32S3 Sense setup; the firmware reports `imu_ok=false`

This directory is intentionally separate from the v1.x AtomS3R firmware because v2.0 changes the hardware platform and camera pin map.

## Configure

Edit `include/user_config.h`:

- `WIFI_SSID`, `WIFI_PASS`
- `COLLECTOR_HOST`, `COLLECTOR_PORT`
- `LED_PWM_PIN` for your external illumination rig

## Build And Upload

```powershell
cd firmware/xiao_esp32s3_sense_streamer_v2
pio run -t upload
pio device monitor
```

Serial output should show:

- Wi-Fi connected and IP address
- PSRAM detected
- Camera init OK
- Streaming enabled

## Collector Compatibility

The firmware sends these required form fields to `POST /upload`:

- `image`
- `frame_id`
- `device_ts_ms`
- `width`, `height`
- `led_pwm`

It also sends v2.0 metadata as extra form fields:

- `firmware_version=2.0.0`
- `hardware_version=v2.0-xiao-esp32s3-sense-ov3660`
- `device_model=seeed-xiao-esp32s3-sense`
- `device_id=xiao-s3-sense-v2`

UDP commands:

```json
{"cmd":"ping"}
{"cmd":"set_led","pwm":128}
{"cmd":"start_stream"}
{"cmd":"stop_stream"}
{"cmd":"set_param","jpeg_quality":20,"target_fps":12}
{"cmd":"reboot"}
```

## Hardware Notes

The camera pin map follows Seeed's XIAO ESP32S3 Sense camera slot documentation:

- XCLK: GPIO10
- SCCB: SDA GPIO40, SCL GPIO39
- PCLK: GPIO13
- VSYNC: GPIO38
- HREF: GPIO47
- D0..D7: GPIO15, GPIO17, GPIO18, GPIO16, GPIO14, GPIO12, GPIO11, GPIO48

Seeed documents that newer XIAO ESP32S3 Sense units use OV3660 after OV2640 discontinuation, and the same camera examples remain applicable.
