#pragma once

// ===============================
// User configuration (EDIT THIS!)
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
