#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>
#include "esp_camera.h"
#include "sensor.h"

#include "user_config.h"
#include "board_xiao_esp32s3_sense_pins.h"

static WiFiUDP Udp;
static bool g_streaming = false;
static uint32_t g_frame_id = 0;
static uint16_t g_target_fps = STREAM_FPS_DEFAULT;
static uint8_t g_jpeg_quality = JPEG_QUALITY_DEFAULT;
static int g_frame_size = FRAME_SIZE_DEFAULT;

static uint8_t g_led_pwm = LED_PWM_DEFAULT;
static const int LEDC_CH = 0;

static void led_init() {
  ledcSetup(LEDC_CH, LED_PWM_FREQ_HZ, LED_PWM_RES_BITS);
  ledcAttachPin(LED_PWM_PIN, LEDC_CH);
  ledcWrite(LEDC_CH, g_led_pwm);
}

static void led_set(uint8_t pwm) {
  g_led_pwm = pwm;
  ledcWrite(LEDC_CH, g_led_pwm);
}

static bool wifi_connect() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.printf("[WiFi] connecting to %s\n", WIFI_SSID);
  const uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
    if (millis() - t0 > 20000) {
      Serial.println("\n[WiFi] timeout");
      return false;
    }
  }

  Serial.printf("\n[WiFi] connected. IP=%s RSSI=%d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  return true;
}

static void udp_init() {
  Udp.begin(UDP_CMD_PORT);
  Serial.printf("[UDP] listening on %u\n", UDP_CMD_PORT);
}

static camera_config_t make_camera_config() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_1;
  config.ledc_timer = LEDC_TIMER_1;

  config.pin_d0 = CAM_PIN_D0;
  config.pin_d1 = CAM_PIN_D1;
  config.pin_d2 = CAM_PIN_D2;
  config.pin_d3 = CAM_PIN_D3;
  config.pin_d4 = CAM_PIN_D4;
  config.pin_d5 = CAM_PIN_D5;
  config.pin_d6 = CAM_PIN_D6;
  config.pin_d7 = CAM_PIN_D7;
  config.pin_xclk = CAM_PIN_XCLK;
  config.pin_pclk = CAM_PIN_PCLK;
  config.pin_vsync = CAM_PIN_VSYNC;
  config.pin_href = CAM_PIN_HREF;
  config.pin_sccb_sda = CAM_PIN_SIOD;
  config.pin_sccb_scl = CAM_PIN_SIOC;
  config.pin_pwdn = CAM_PIN_PWDN;
  config.pin_reset = CAM_PIN_RESET;

  // Keep camera SCCB separate from Arduino Wire defaults.
  config.sccb_i2c_port = 1;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = (framesize_t)g_frame_size;
  config.jpeg_quality = g_jpeg_quality;
  config.fb_count = 2;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  return config;
}

static void tune_ov3660(sensor_t* sensor) {
  if (!sensor) return;

  Serial.printf("[CAM] sensor PID: 0x%04x\n", sensor->id.PID);
  sensor->set_framesize(sensor, (framesize_t)g_frame_size);
  sensor->set_quality(sensor, g_jpeg_quality);

  if (sensor->id.PID == OV3660_PID) {
    // Common OV3660 orientation/color defaults used by ESP32 camera examples.
    sensor->set_vflip(sensor, 1);
    sensor->set_brightness(sensor, 1);
    sensor->set_saturation(sensor, -2);
  }
}

static bool camera_init_once() {
  if (!psramFound()) {
    Serial.println("[CAM] PSRAM not found. XIAO ESP32S3 Sense should have PSRAM; check qio_opi setting.");
  } else {
    Serial.printf("[CAM] PSRAM OK. size=%u\n", ESP.getPsramSize());
  }

  camera_config_t config = make_camera_config();
  Serial.printf("[CAM] pins: SDA=%d SCL=%d VSYNC=%d HREF=%d PCLK=%d XCLK=%d D0=%d D1=%d D2=%d D3=%d D4=%d D5=%d D6=%d D7=%d\n",
                CAM_PIN_SIOD, CAM_PIN_SIOC, CAM_PIN_VSYNC, CAM_PIN_HREF, CAM_PIN_PCLK, CAM_PIN_XCLK,
                CAM_PIN_D0, CAM_PIN_D1, CAM_PIN_D2, CAM_PIN_D3, CAM_PIN_D4, CAM_PIN_D5, CAM_PIN_D6, CAM_PIN_D7);

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] init failed: 0x%x\n", (int)err);
    return false;
  }

  tune_ov3660(esp_camera_sensor_get());
  Serial.println("[CAM] init OK");
  return true;
}

static bool camera_init_with_retry() {
  const uint8_t max_tries = CAM_INIT_MAX_RETRIES < 1 ? 1 : CAM_INIT_MAX_RETRIES;
  for (uint8_t i = 0; i < max_tries; i++) {
    Serial.printf("[CAM] init try %u/%u\n", (unsigned)(i + 1), (unsigned)max_tries);
    if (camera_init_once()) return true;
    esp_camera_deinit();
    delay(CAM_RETRY_DELAY_MS);
  }
  return false;
}

static bool http_upload_frame(camera_fb_t* fb) {
  if (!fb || fb->format != PIXFORMAT_JPEG) {
    Serial.println("[HTTP] frame is not JPEG");
    return false;
  }

  WiFiClient client;
  client.setTimeout(4000);

  if (!client.connect(COLLECTOR_HOST, COLLECTOR_PORT)) {
    Serial.println("[HTTP] connect failed");
    return false;
  }

  String boundary = "----gbBoundary";
  boundary += String((uint32_t)esp_random(), HEX);

  auto part_field = [&](const char* name, const String& value) -> String {
    String p;
    p += "--" + boundary + "\r\n";
    p += "Content-Disposition: form-data; name=\"";
    p += name;
    p += "\"\r\n\r\n";
    p += value;
    p += "\r\n";
    return p;
  };

  String head;
  head.reserve(768);
  head += part_field("frame_id", String(g_frame_id));
  head += part_field("device_ts_ms", String((uint32_t)millis()));
  head += part_field("width", String(fb->width));
  head += part_field("height", String(fb->height));
  head += part_field("led_pwm", String(g_led_pwm));
  head += part_field("firmware_version", FIRMWARE_VERSION);
  head += part_field("hardware_version", HARDWARE_VERSION);
  head += part_field("device_model", DEVICE_MODEL);
  head += part_field("device_id", DEVICE_ID);

  head += "--" + boundary + "\r\n";
  head += "Content-Disposition: form-data; name=\"image\"; filename=\"frame.jpg\"\r\n";
  head += "Content-Type: image/jpeg\r\n\r\n";

  String tail;
  tail.reserve(64);
  tail += "\r\n--" + boundary + "--\r\n";

  const uint32_t content_length = head.length() + fb->len + tail.length();

  client.print(String("POST ") + COLLECTOR_PATH + " HTTP/1.1\r\n");
  client.print(String("Host: ") + COLLECTOR_HOST + "\r\n");
  client.print("User-Agent: xiao-esp32s3-sense-v2-streamer\r\n");
  client.print(String("Content-Type: multipart/form-data; boundary=") + boundary + "\r\n");
  client.print(String("Content-Length: ") + content_length + "\r\n");
  client.print("Connection: close\r\n\r\n");

  client.print(head);
  client.write(fb->buf, fb->len);
  client.print(tail);

  const uint32_t t0 = millis();
  while (client.connected() && millis() - t0 < 1000) {
    while (client.available()) {
      (void)client.read();
    }
    break;
  }
  client.stop();
  return true;
}

static void send_udp_response(const IPAddress& ip, uint16_t port, const JsonDocument& doc) {
  char out[384];
  size_t n = serializeJson(doc, out, sizeof(out));
  Udp.beginPacket(ip, port);
  Udp.write((const uint8_t*)out, n);
  Udp.endPacket();
}

static void handle_udp_cmd() {
  int packetSize = Udp.parsePacket();
  if (packetSize <= 0) return;

  char buf[512];
  int len = Udp.read(buf, sizeof(buf) - 1);
  if (len <= 0) return;
  buf[len] = '\0';

  JsonDocument in;
  DeserializationError err = deserializeJson(in, buf);
  JsonDocument out;

  IPAddress rip = Udp.remoteIP();
  uint16_t rport = Udp.remotePort();

  if (err) {
    out["ok"] = false;
    out["error"] = "json_parse_failed";
    send_udp_response(rip, rport, out);
    return;
  }

  const char* cmd = in["cmd"] | "";
  out["cmd"] = cmd;

  if (strcmp(cmd, "ping") == 0) {
    out["ok"] = true;
    out["device_ts_ms"] = (uint32_t)millis();
    out["ip"] = WiFi.localIP().toString();
    out["streaming"] = g_streaming;
    out["led_pwm"] = g_led_pwm;
    out["imu_ok"] = false;
    out["firmware_version"] = FIRMWARE_VERSION;
    out["hardware_version"] = HARDWARE_VERSION;
    out["device_model"] = DEVICE_MODEL;
    out["device_id"] = DEVICE_ID;
  } else if (strcmp(cmd, "start_stream") == 0) {
    g_streaming = true;
    out["ok"] = true;
    out["streaming"] = true;
  } else if (strcmp(cmd, "stop_stream") == 0) {
    g_streaming = false;
    out["ok"] = true;
    out["streaming"] = false;
  } else if (strcmp(cmd, "set_led") == 0) {
    int pwm = in["pwm"] | -1;
    if (pwm < 0) pwm = 0;
    if (pwm > 255) pwm = 255;
    led_set((uint8_t)pwm);
    out["ok"] = true;
    out["pwm"] = pwm;
  } else if (strcmp(cmd, "set_param") == 0) {
    if (in["target_fps"].is<int>()) {
      int fps = in["target_fps"] | (int)g_target_fps;
      if (fps < 1) fps = 1;
      if (fps > 30) fps = 30;
      g_target_fps = (uint16_t)fps;
      out["target_fps"] = fps;
    }

    if (in["jpeg_quality"].is<int>()) {
      int q = in["jpeg_quality"] | (int)g_jpeg_quality;
      if (q < 2) q = 2;
      if (q > 63) q = 63;
      g_jpeg_quality = (uint8_t)q;
      sensor_t* sensor = esp_camera_sensor_get();
      if (sensor) sensor->set_quality(sensor, g_jpeg_quality);
      out["jpeg_quality"] = q;
    }

    out["ok"] = true;
  } else if (strcmp(cmd, "reboot") == 0) {
    out["ok"] = true;
    send_udp_response(rip, rport, out);
    delay(100);
    ESP.restart();
    return;
  } else {
    out["ok"] = false;
    out["error"] = "unknown_cmd";
  }

  send_udp_response(rip, rport, out);
}

static void stream_loop_once() {
  if (!g_streaming) return;

  const uint32_t frame_interval_ms = g_target_fps > 0 ? (1000UL / g_target_fps) : 100;
  const uint32_t t0 = millis();

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAM] capture failed");
    delay(50);
    return;
  }

  bool ok = http_upload_frame(fb);
  esp_camera_fb_return(fb);

  if (!ok) {
    delay(200);
    return;
  }

  g_frame_id++;

  const uint32_t dt = millis() - t0;
  if (dt < frame_interval_ms) {
    delay(frame_interval_ms - dt);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("== Goosebumps Edge AI v2.0 XIAO ESP32S3 Sense Streamer ==");
  Serial.printf("[SYS] firmware=%s hardware=%s model=%s id=%s\n", FIRMWARE_VERSION, HARDWARE_VERSION, DEVICE_MODEL, DEVICE_ID);

  led_init();
  Serial.println("[LED] init OK");

  while (!wifi_connect()) {
    delay(2000);
  }

  udp_init();

  if (!camera_init_with_retry()) {
    Serial.println("[CAM] init failed after retries. restarting...");
    delay(1000);
    ESP.restart();
  }

  g_streaming = true;
  Serial.println("[SYS] streaming=ON (default). Use UDP cmd stop_stream to stop.");
}

void loop() {
  handle_udp_cmd();
  stream_loop_once();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] disconnected, reconnecting...");
    g_streaming = false;
    WiFi.disconnect(true);
    delay(300);
    while (!wifi_connect()) {
      delay(1500);
    }
    g_streaming = true;
  }
}
