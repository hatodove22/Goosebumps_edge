#pragma once

// ===============================
// Goosebumps Edge AI v2.0
// ===============================
// Hardware change from the v1.x AtomS3R reference:
// Seeed Studio XIAO ESP32S3 Sense + OV3660 camera.

static const char* FIRMWARE_VERSION = "2.0.0";
static const char* HARDWARE_VERSION = "v2.0-xiao-esp32s3-sense-ov3660";
static const char* DEVICE_MODEL = "seeed-xiao-esp32s3-sense";
static const char* DEVICE_ID = "xiao-s3-sense-v2";

// ===============================
// User configuration (EDIT THIS)
// ===============================

// Wi-Fi credentials
static const char* WIFI_SSID = "YOUR_SSID";
static const char* WIFI_PASS = "YOUR_PASSWORD";

// Collector PC (FastAPI) endpoint
// Example: "192.168.1.10"
static const char* COLLECTOR_HOST = "192.168.1.10";
static const uint16_t COLLECTOR_PORT = 8000;
static const char* COLLECTOR_PATH = "/upload";

// UDP command listener port (PC -> device)
static const uint16_t UDP_CMD_PORT = 3333;

// Streaming defaults
static const uint16_t STREAM_FPS_DEFAULT = 12;
static const uint8_t JPEG_QUALITY_DEFAULT = 20;  // 2..63 (lower=better quality, larger file)

// Camera frame size (esp_camera framesize_t)
// QVGA=5, VGA=8, SVGA=9, XGA=10, SXGA=12, UXGA=13.
// VGA is a practical default for Wi-Fi upload and preview.
static const int FRAME_SIZE_DEFAULT = 8; // FRAMESIZE_VGA

// External LED PWM for the illumination rig.
// Choose a free XIAO pin that is not used by the Sense camera slot.
static const int LED_PWM_PIN = 2;
static const uint32_t LED_PWM_FREQ_HZ = 5000;
static const uint8_t LED_PWM_RES_BITS = 8;
static const uint8_t LED_PWM_DEFAULT = 120;

// Camera init behavior
static const uint8_t CAM_INIT_MAX_RETRIES = 5;
static const uint32_t CAM_RETRY_DELAY_MS = 300;
