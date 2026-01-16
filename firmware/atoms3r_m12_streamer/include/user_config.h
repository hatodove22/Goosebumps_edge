#pragma once

// ===============================
// Camera variant selection
// ===============================
//
// AtomS3R-CAM (non-M12) uses GC0308 (0.3MP) and does NOT output JPEG natively.
// We capture RGB565 and encode to JPEG in software (lower FPS, higher CPU).
//
// AtomS3R Cam M12 kit uses OV3660 (3MP) and can output JPEG directly.
//
// Set CAMERA_VARIANT to match your hardware.
//
//   0 = AtomS3R-CAM (GC0308, non-M12)
//   1 = AtomS3R Cam M12 kit (OV3660, M12)
//
static const int CAMERA_VARIANT = 0;

// ===============================
// User configuration (EDIT THIS!)
// ===============================

// Wi-Fi credentials
static const char* WIFI_SSID = "doves_persosal_AP";
static const char* WIFI_PASS = "nicola22";

// Collector PC (FastAPI) endpoint
// Example: "192.168.1.10"
static const char* COLLECTOR_HOST = "192.168.137.1";
static const uint16_t COLLECTOR_PORT = 8000;
static const char* COLLECTOR_PATH = "/upload";

// UDP command listener port (PC -> device)
static const uint16_t UDP_CMD_PORT = 3333;

// Streaming defaults
static const uint16_t STREAM_FPS_DEFAULT = 12;   // target fps
static const uint8_t JPEG_QUALITY_DEFAULT = 20;  // 0..63 (lower=better quality, larger file)

// Camera frame size (esp_camera framesize_t)
// QVGA = 320x240, VGA = 640x480, SVGA = 800x600, etc.
static const int FRAME_SIZE_DEFAULT = 5; // FRAMESIZE_QVGA (enum value)

// External LED PWM (for your adjustable illumination)
// Choose from bottom GPIO: G5/G6/G7/G8/G38/G39
static const int LED_PWM_PIN = 2;          // GPIO2 (grove pin)
static const uint32_t LED_PWM_FREQ_HZ = 5000; // adjust if banding occurs
static const uint8_t LED_PWM_RES_BITS = 8; // 0..255
static const uint8_t LED_PWM_DEFAULT = 120;

// ===============================
// Camera self-test (optional)
// ===============================
// Enable to capture a few frames at boot and print status to Serial.
static const bool ENABLE_CAMERA_SELF_TEST = false;
static const uint8_t CAMERA_SELF_TEST_FRAMES = 3;
