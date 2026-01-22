#pragma once

// ===============================
// Hardware variant
// ===============================
// AtomS3R-CAM (GC0308) uses RGB565 output (no native JPEG).
// Set GPIO18 LOW (POWER_N) before esp_camera_init().
static const int CAMERA_VARIANT = 0; // 0 = AtomS3R-CAM (GC0308)

// ===============================
// Wi-Fi / Collector
// ===============================
// NOTE: Replace with your Wi-Fi credentials.
static const char* WIFI_SSID = "doves_persosal_AP";
static const char* WIFI_PASS = "nicola22";

// Collector PC endpoint (used for optional upload/events)
static const char* COLLECTOR_HOST = "192.168.137.1";
static const uint16_t COLLECTOR_PORT = 8000;
static const char* COLLECTOR_UPLOAD_PATH = "/upload";
static const char* COLLECTOR_EVENT_PATH = "/event";

// UDP command listener port (PC -> device)
static const uint16_t UDP_CMD_PORT = 3333;

// ===============================
// On-device HTTP status/control API
// ===============================
// Enables a lightweight HTTP server on the device.
// - GET  /status   : JSON status + latest inference
// - POST /control  : JSON control (camera on/off, zscore on/off, thresholds...)
// - GET  /snapshot : ROI snapshot (JPEG, on-demand)
static const bool ENABLE_HTTP_SERVER = true;
static const uint16_t HTTP_SERVER_PORT = 80;

// Device identity (shown in /status)
static const char* DEVICE_ID = "atoms3r_cam_01";
static const char* FW_VERSION = "gb_atoms3r_cam_infer_v2.2";

// Snapshot settings
// JPEG quality: 2..63 (lower = higher quality, larger size)
static const uint8_t SNAPSHOT_JPEG_QUALITY = 20;

// ===============================
// z-score event detection (on-device)
// ===============================
// If DEFAULT_USE_ZSCORE=true, the device uses z-score hysteresis for state
// detection instead of probability hysteresis.
// z is computed from p_ema using an EMA mean/variance (lightweight).
static const bool DEFAULT_USE_ZSCORE = true;
static const float ZSCORE_EMA_TAU_SEC = 30.0f;  // baseline adaptation speed
static const float ZSCORE_ON_DEFAULT  = 4.0f;
static const float ZSCORE_OFF_DEFAULT = 3.0f;
static const float ZSCORE_EPS = 1e-3f;

// ===============================
// Optional telemetry push (device -> PC)
// ===============================
// If enabled, the device sends JSON telemetry periodically via UDP.
static const bool ENABLE_TELEMETRY_PUSH = false;
static const char* TELEMETRY_HOST_DEFAULT = "192.168.137.1";
static const uint16_t TELEMETRY_UDP_PORT_DEFAULT = 9001;
static const float TELEMETRY_HZ_DEFAULT = 10.0f;

// ===============================
// Camera stream defaults
// ===============================
// If ENABLE_FRAME_UPLOAD=false, the device will NOT upload frames.
// It will still capture frames locally for inference.
static const bool ENABLE_FRAME_UPLOAD = true;

static const uint16_t TARGET_FPS_DEFAULT = 12;
static const uint8_t JPEG_QUALITY_DEFAULT = 20; // used only when encoding RGB565->JPEG

// esp_camera framesize_t enum value
// 5 = FRAMESIZE_QVGA (320x240)
static const int FRAME_SIZE_DEFAULT = 5;

// ===============================
// Illumination LED (external)
// ===============================
// If you use an external LED for illumination, connect it to a bottom GPIO.
// AtomS3R-CAM bottom GPIO: G5/G6/G7/G8/G38/G39 (see M5 docs)
static const int LED_PWM_PIN = 2;            // example: Grove G2
static const uint32_t LED_PWM_FREQ_HZ = 5000;
static const uint8_t LED_PWM_RES_BITS = 8;
static const uint8_t LED_PWM_DEFAULT = 60;

// ===============================
// Camera init robustness
// ===============================
// Some AtomS3R-CAM boards show occasional "Camera probe failed" (ESP_ERR_NOT_FOUND)
// at boot. To mitigate this, we power-cycle the camera enable pin (POWER_N) and
// retry esp_camera_init() a few times.
static const uint8_t CAM_INIT_MAX_RETRIES = 5;
static const uint16_t CAM_POWER_OFF_DELAY_MS = 40;   // POWER_N=HIGH duration
static const uint16_t CAM_POWER_ON_DELAY_MS  = 400;  // wait after POWER_N=LOW
static const uint16_t CAM_RETRY_DELAY_MS     = 200;  // between retries
static const bool CAM_INIT_BEFORE_WIFI       = true; // reduces inrush-related failures
static const bool CAM_RESTART_ON_INIT_FAIL   = true; // reboot after all retries fail

// ===============================
// Inference config (LBP+LogReg)
// ===============================
// ROI is a fixed center square (matches dataset meta.json default)
static const int ROI_SIZE_PX = 160;   // center ROI size in the captured frame
static const int INPUT_SIZE = 64;     // downsample ROI to INPUT_SIZE x INPUT_SIZE

// Probability smoothing (EMA)
static const float PROB_EMA_TAU_SEC = 0.8f;

// Binary decision with hysteresis
// - Default uses model threshold as ON threshold; OFF threshold is lower.
static const float HYSTERESIS_DELTA = 0.10f; // thr_off = thr_on - delta

// Optional: send pred on/off events to Collector (/event)
static const bool ENABLE_EVENT_POST = true;

// Optional: print every N frames
static const uint32_t PRINT_EVERY_N_FRAMES = 5;

// Optional: calibration via UDP (calib_start/calib_done)
// If calibration is used, thresholds are overridden by: thr_on = mean + k_on*std
static const float CALIB_K_ON = 3.0f;
static const float CALIB_K_OFF = 2.0f;
static const uint32_t CALIB_MIN_MS = 5000; // minimum calibration duration
