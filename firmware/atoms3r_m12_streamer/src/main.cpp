// Fix for AtomS3R-CAM (GC0308) + IMU:
// 1) Initialize CAMERA before IMU/Wire to avoid I2C pin routing conflicts.
// 2) Force camera SCCB onto I2C port 1 so it does not share I2C0 with Arduino Wire.
// These changes address frequent ESP_ERR_NOT_FOUND (0x105) probe failures.

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>
#include "esp_camera.h"
#include "img_converters.h"   // fmt2jpg
#include <Wire.h>

// IMU (BMI270)
#include "SparkFun_BMI270_Arduino_Library.h"

#include "user_config.h"
#include "board_atoms3r_m12_pins.h"

// ---------- Runtime state ----------
static WiFiUDP Udp;
static bool g_streaming = false;
static uint32_t g_frame_id = 0;
static uint16_t g_target_fps = STREAM_FPS_DEFAULT;
static uint8_t g_jpeg_quality = JPEG_QUALITY_DEFAULT;
static int g_frame_size = FRAME_SIZE_DEFAULT;

static uint8_t g_led_pwm = LED_PWM_DEFAULT;
static const int LEDC_CH = 0;

// Camera power timing (some AtomS3R-CAM units show SCCB probe races on cold boot)
static uint32_t g_cam_power_on_ms = 0;
static const bool ENABLE_CAM_I2C_SCAN = false;  // debug only; often returns "no devices" before XCLK is running

// IMU runtime state
static BMI270 g_imu;
static bool g_imu_ok = false;
static float g_last_ax = NAN, g_last_ay = NAN, g_last_az = NAN;
static float g_last_gx = NAN, g_last_gy = NAN, g_last_gz = NAN;
static float g_last_gnorm = NAN;

// ---------- Helpers ----------
static bool is_m12_variant() {
  return (CAMERA_VARIANT == 1);
}

static void camera_power_enable(bool force_restart_timer = false) {
  pinMode(18, OUTPUT);
  digitalWrite(18, LOW);  // enable camera power
  if (force_restart_timer || g_cam_power_on_ms == 0) {
    g_cam_power_on_ms = millis();
  }
}

static void camera_power_disable() {
  pinMode(18, OUTPUT);
  digitalWrite(18, HIGH);  // disable camera power (POWER_N active-low)
}

static void camera_wait_min_on_time(uint32_t min_on_ms) {
  if (g_cam_power_on_ms == 0) return;
  const uint32_t elapsed = millis() - g_cam_power_on_ms;
  if (elapsed < min_on_ms) {
    delay(min_on_ms - elapsed);
  }
}

static void camera_power_cycle(uint32_t off_ms = 50, uint32_t min_on_ms = 500) {
  camera_power_disable();
  delay(off_ms);
  g_cam_power_on_ms = 0;
  camera_power_enable(true);
  camera_wait_min_on_time(min_on_ms);
}

static void scan_camera_i2c_once() {
  // NOTE:
  // Many camera sensors require XCLK to be running before SCCB responds.
  // Therefore, an I2C scan performed *before* esp_camera_init() may legitimately find no devices.
  // This function is kept only for debugging and is disabled by default.
  // Use I2C port 1 for CAM_SDA/CAM_SCL (GPIO12/GPIO9) to avoid Wire (IMU) on I2C0.
  TwoWire WireCam(1);
  WireCam.begin(CAM_PIN_SIOD, CAM_PIN_SIOC, 100000);
  uint8_t found = 0;
  Serial.printf("[CAM] I2C scan on SDA=%d SCL=%d ...\n", CAM_PIN_SIOD, CAM_PIN_SIOC);
  for (uint8_t addr = 8; addr < 120; addr++) {
    WireCam.beginTransmission(addr);
    uint8_t err = WireCam.endTransmission();
    if (err == 0) {
      Serial.printf("[CAM] I2C device found at 0x%02X\n", addr);
      found++;
    }
  }
  if (found == 0) {
    Serial.println("[CAM] I2C scan found no devices (check POWER_N, wiring, pins)"); 
  }
  WireCam.end();
}

static void led_init() {
  ledcSetup(LEDC_CH, LED_PWM_FREQ_HZ, LED_PWM_RES_BITS);
  ledcAttachPin(LED_PWM_PIN, LEDC_CH);
  ledcWrite(LEDC_CH, g_led_pwm);
}

static void led_set(uint8_t pwm) {
  g_led_pwm = pwm;
  ledcWrite(LEDC_CH, g_led_pwm);
}

static bool imu_init() {
  // BMI270 uses SYS_SDA/SYS_SCL (GPIO45/GPIO0) on AtomS3R-M12.
  // IMPORTANT: Use the correct pins; Wire.begin() defaults may not match.
  Wire.begin(IMU_PIN_SDA, IMU_PIN_SCL);
  Wire.setClock(400000);

  Serial.printf("[IMU] init (BMI270) SDA=%d SCL=%d addr=0x68\n", IMU_PIN_SDA, IMU_PIN_SCL);

  // Retry a few times to avoid sporadic I2C startup failures
  for (int i = 0; i < 5; i++) {
    int8_t err = g_imu.beginI2C(BMI2_I2C_PRIM_ADDR);  // 0x68
    if (err == BMI2_OK) {
      g_imu_ok = true;
      Serial.println("[IMU] BMI270 connected");
      return true;
    }
    Serial.printf("[IMU] beginI2C failed (err=%d). retry...\n", (int)err);
    delay(250);
  }

  g_imu_ok = false;
  Serial.println("[IMU] BMI270 not found; continuing without IMU");
  return false;
}

static void imu_update_once() {
  if (!g_imu_ok) return;

  // NOTE: SparkFun BMI270 library requires calling getSensorData() before reading fields.
  g_imu.getSensorData();

  g_last_ax = g_imu.data.accelX;
  g_last_ay = g_imu.data.accelY;
  g_last_az = g_imu.data.accelZ;
  g_last_gx = g_imu.data.gyroX;
  g_last_gy = g_imu.data.gyroY;
  g_last_gz = g_imu.data.gyroZ;
  g_last_gnorm = sqrtf(g_last_gx * g_last_gx + g_last_gy * g_last_gy + g_last_gz * g_last_gz);
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
  // Ensure camera power is enabled (especially for AtomS3R-CAM / GC0308).
  camera_power_enable(false);

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_1;     // camera uses different channel internally
  config.ledc_timer   = LEDC_TIMER_1;

  config.pin_d0       = CAM_PIN_D0;
  config.pin_d1       = CAM_PIN_D1;
  config.pin_d2       = CAM_PIN_D2;
  config.pin_d3       = CAM_PIN_D3;
  config.pin_d4       = CAM_PIN_D4;
  config.pin_d5       = CAM_PIN_D5;
  config.pin_d6       = CAM_PIN_D6;
  config.pin_d7       = CAM_PIN_D7;
  config.pin_xclk     = CAM_PIN_XCLK;
  config.pin_pclk     = CAM_PIN_PCLK;
  config.pin_vsync    = CAM_PIN_VSYNC;
  config.pin_href     = CAM_PIN_HREF;
  config.pin_sccb_sda = CAM_PIN_SIOD;
  config.pin_sccb_scl = CAM_PIN_SIOC;
  // IMPORTANT:
  // AtomS3R-CAM pin map labels GPIO18 as POWER_N (active-low enable).
  // esp_camera pin_pwdn is active-high PWDN; passing POWER_N here can disable the camera during probe.
  // Therefore we keep pin_pwdn unused and control POWER_N ourselves.
  config.pin_pwdn     = -1;
  config.pin_reset    = CAM_PIN_RESET;

  // Put camera SCCB (CAM_SDA/CAM_SCL) on I2C port 1 to avoid sharing I2C0 with Arduino Wire (IMU).
  config.sccb_i2c_port = 1;

  // For AtomS3R-CAM (GC0308), M5Stack docs suggest XCLK up to 20MHz; start at 20MHz.
  config.xclk_freq_hz = is_m12_variant() ? 20000000 : 20000000;

  // M12(OV3660): native JPEG
  // non-M12(GC0308): no native JPEG -> capture RGB565, then encode to JPEG in software
  if (is_m12_variant()) {
    config.pixel_format = PIXFORMAT_JPEG;
  } else {
    config.pixel_format = PIXFORMAT_RGB565;
  }

  config.frame_size   = (framesize_t)g_frame_size;
  config.jpeg_quality = g_jpeg_quality;  // 0..63 (lower=better, larger)
  config.fb_count     = 2;               // double buffer for stability
  config.fb_location  = CAMERA_FB_IN_PSRAM;
  config.grab_mode    = CAMERA_GRAB_LATEST;

  return config;
}

static bool camera_init() {
  if (!psramFound()) {
    Serial.println("[CAM] PSRAM not found. This board should have PSRAM. Check PlatformIO memory_type=qio_opi");
  } else {
    Serial.printf("[CAM] PSRAM OK. size=%u\n", ESP.getPsramSize());
  }

  camera_config_t cfg = make_camera_config();

  // Ensure the sensor has been powered long enough (helps cold-boot SCCB probe races).
  camera_wait_min_on_time(500);

  Serial.printf("[CAM] pins: SDA=%d SCL=%d VSYNC=%d HREF=%d PCLK=%d XCLK=%d D0=%d D1=%d D2=%d D3=%d D4=%d D5=%d D6=%d D7=%d POWER_N=%d\n",
                CAM_PIN_SIOD, CAM_PIN_SIOC, CAM_PIN_VSYNC, CAM_PIN_HREF, CAM_PIN_PCLK, CAM_PIN_XCLK,
                CAM_PIN_D0, CAM_PIN_D1, CAM_PIN_D2, CAM_PIN_D3, CAM_PIN_D4, CAM_PIN_D5, CAM_PIN_D6, CAM_PIN_D7,
                18);
  Serial.printf("[CAM] cfg: xclk=%d pixel_format=%d framesize=%d jpeg_quality=%d pin_pwdn=%d sccb_port=%d\n",
                (int)cfg.xclk_freq_hz, (int)cfg.pixel_format, (int)cfg.frame_size, (int)cfg.jpeg_quality, (int)cfg.pin_pwdn, (int)cfg.sccb_i2c_port);

  const int kMaxAttempts = 5;
  esp_err_t err = ESP_FAIL;
  for (int attempt = 1; attempt <= kMaxAttempts; attempt++) {
    Serial.printf("[CAM] init attempt %d/%d\n", attempt, kMaxAttempts);
    if (ENABLE_CAM_I2C_SCAN && attempt == 1) {
      scan_camera_i2c_once();
    }
    err = esp_camera_init(&cfg);
    if (err == ESP_OK) break;

    Serial.printf("[CAM] init failed: 0x%x\n", (int)err);
    // Best-effort cleanup and a short power cycle to reset the sensor
    esp_camera_deinit();
    camera_power_cycle(80, 600);
    cfg = make_camera_config();
    camera_wait_min_on_time(500);
  }

  if (err != ESP_OK) {
    Serial.printf("[CAM] init ultimately failed after %d attempts. last_err=0x%x\n", kMaxAttempts, (int)err);
    return false;
  }

  sensor_t* s = esp_camera_sensor_get();
  // basic tuning (optional)
  s->set_framesize(s, (framesize_t)g_frame_size);

  if (is_m12_variant()) {
    // JPEG quality is meaningful only when camera outputs JPEG
    s->set_quality(s, g_jpeg_quality);
  }

  Serial.println("[CAM] init OK");
  return true;
}

static void camera_deinit() {
  esp_camera_deinit();
}

// Convert non-JPEG frame buffer to JPEG (software encoding)
// Returns true on success; caller must free(*out_buf) when true.
static bool fb_to_jpeg(const camera_fb_t* fb, uint8_t jpeg_quality, uint8_t** out_buf, size_t* out_len) {
  *out_buf = nullptr;
  *out_len = 0;

  if (!fb || !fb->buf || fb->len == 0) return false;

  if (fb->format == PIXFORMAT_JPEG) {
    // Should not happen here in non-M12 path, but keep safe.
    *out_buf = (uint8_t*)fb->buf;
    *out_len = fb->len;
    return true;
  }

  // Encode RGB565 -> JPEG
  // Note: fmt2jpg allocates output buffer; free() it after upload.
  bool ok = fmt2jpg(
    fb->buf, fb->len,
    fb->width, fb->height,
    fb->format,
    jpeg_quality,
    out_buf,
    out_len
  );
  return ok;
}

// Build and send multipart/form-data request
static bool http_upload_frame(camera_fb_t* fb) {
  WiFiClient client;
  client.setTimeout(4000);

  if (!client.connect(COLLECTOR_HOST, COLLECTOR_PORT)) {
    Serial.println("[HTTP] connect failed");
    return false;
  }

  // Ensure we always send JPEG to the Collector.
  uint8_t* jpg_buf = nullptr;
  size_t jpg_len = 0;
  bool need_free = false;

  if (fb->format == PIXFORMAT_JPEG) {
    jpg_buf = fb->buf;
    jpg_len = fb->len;
    need_free = false;
  } else {
    // For GC0308 (RGB565), encode in software.
    if (!fb_to_jpeg(fb, g_jpeg_quality, &jpg_buf, &jpg_len)) {
      Serial.println("[JPEG] encode failed");
      return false;
    }
    need_free = true;
  }

  String boundary = "----gbBoundary";
  boundary += String((uint32_t)esp_random(), HEX);

  // Parts (small fields as String; image sent as raw bytes)
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
  head.reserve(512);
  head += part_field("frame_id", String(g_frame_id));
  head += part_field("device_ts_ms", String((uint32_t)millis()));
  head += part_field("width", String(fb->width));
  head += part_field("height", String(fb->height));
  head += part_field("led_pwm", String(g_led_pwm));

  // IMU fields (optional; only sent when BMI270 was initialized)
  if (g_imu_ok) {
    // accel in g, gyro in deg/s (per SparkFun library)
    if (isfinite(g_last_ax)) head += part_field("ax", String(g_last_ax, 6));
    if (isfinite(g_last_ay)) head += part_field("ay", String(g_last_ay, 6));
    if (isfinite(g_last_az)) head += part_field("az", String(g_last_az, 6));
    if (isfinite(g_last_gx)) head += part_field("gx", String(g_last_gx, 6));
    if (isfinite(g_last_gy)) head += part_field("gy", String(g_last_gy, 6));
    if (isfinite(g_last_gz)) head += part_field("gz", String(g_last_gz, 6));
    if (isfinite(g_last_gnorm)) head += part_field("g_norm", String(g_last_gnorm, 6));
  }

  // image header
  head += "--" + boundary + "\r\n";
  head += "Content-Disposition: form-data; name=\"image\"; filename=\"frame.jpg\"\r\n";
  head += "Content-Type: image/jpeg\r\n\r\n";

  String tail;
  tail.reserve(64);
  tail += "\r\n--" + boundary + "--\r\n";

  const uint32_t content_length = head.length() + jpg_len + tail.length();

  // HTTP header
  client.print(String("POST ") + COLLECTOR_PATH + " HTTP/1.1\r\n");
  client.print(String("Host: ") + COLLECTOR_HOST + "\r\n");
  client.print("User-Agent: atoms3r-m12-streamer\r\n");
  client.print(String("Content-Type: multipart/form-data; boundary=") + boundary + "\r\n");
  client.print(String("Content-Length: ") + content_length + "\r\n");
  client.print("Connection: close\r\n\r\n");

  // body
  client.print(head);
  client.write(jpg_buf, jpg_len);
  client.print(tail);

  // Read response (best effort)
  uint32_t t0 = millis();
  while (client.connected() && millis() - t0 < 1500) {
    while (client.available()) {
      String line = client.readStringUntil('\n');
      // Uncomment for debugging:
      // Serial.println(line);
      if (line == "\r") break;
    }
    break;
  }
  client.stop();

  if (need_free && jpg_buf) {
    free(jpg_buf);
  }
  return true;
}

static void send_udp_response(const IPAddress& ip, uint16_t port, const JsonDocument& doc) {
  char out[256];
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

  StaticJsonDocument<256> in;
  DeserializationError err = deserializeJson(in, buf);
  StaticJsonDocument<256> out;

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
    out["imu_ok"] = g_imu_ok;
    if (g_imu_ok) {
      out["g_norm"] = g_last_gnorm;
    }
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
    bool ok = true;

    if (in.containsKey("target_fps")) {
      int fps = in["target_fps"] | (int)g_target_fps;
      if (fps < 1) fps = 1;
      if (fps > 30) fps = 30;
      g_target_fps = (uint16_t)fps;
      out["target_fps"] = fps;
    }

    if (in.containsKey("jpeg_quality")) {
      int q = in["jpeg_quality"] | (int)g_jpeg_quality;
      if (q < 2) q = 2;
      if (q > 63) q = 63;
      g_jpeg_quality = (uint8_t)q;
      if (is_m12_variant()) {
        sensor_t* s = esp_camera_sensor_get();
        if (s) s->set_quality(s, g_jpeg_quality);
      }
      out["jpeg_quality"] = q;
    }

    out["ok"] = ok;
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

  const uint32_t frame_interval_ms = (g_target_fps > 0) ? (1000UL / g_target_fps) : 100;
  const uint32_t t0 = millis();

  // Sample IMU once per frame (best-effort). We sample before capture so the
  // motion estimate roughly corresponds to the image.
  imu_update_once();

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAM] capture failed");
    delay(50);
    return;
  }

  bool ok = http_upload_frame(fb);
  esp_camera_fb_return(fb);

  if (!ok) {
    // Mild backoff on failure
    delay(200);
    return;
  }

  g_frame_id++;

  const uint32_t dt = millis() - t0;
  if (dt < frame_interval_ms) {
    delay(frame_interval_ms - dt);
  }
}

// ---------- Arduino entry ----------
void setup() {
  // ESP32-S3 USB CDC初期化には時間がかかる場合があるため、十分な待機時間を確保
  Serial.begin(115200);
  delay(1000);  // USB CDC初期化待機時間を延長

  Serial.println("\n== AtomS3R-M12 Streamer ==");
  Serial.println("[DEBUG] Serial initialized");

  // Power on camera early. Some units fail SCCB probe on cold boot unless the sensor
  // has had enough time powered before esp_camera_init().
  camera_power_enable(true);
  Serial.flush();
  
  Serial.println("[DEBUG] Starting LED init...");
  led_init();
  Serial.println("[DEBUG] LED init OK");
  Serial.flush();

  Serial.println("[DEBUG] Starting WiFi connect...");
  if (!wifi_connect()) {
    Serial.println("[DEBUG] WiFi connect failed, retrying...");
    // keep retrying
    while (!wifi_connect()) {
      delay(2000);
    }
  }
  Serial.println("[DEBUG] WiFi connected");
  Serial.flush();

  Serial.println("[DEBUG] Starting UDP init...");
  udp_init();
  Serial.println("[DEBUG] UDP init OK");
  Serial.flush();

  Serial.println("[DEBUG] Starting camera init...");
  if (!camera_init()) {
    Serial.println("[CAM] init failed. HALT for debug (no reboot).");
    while (true) { delay(1000); }
  }

  // IMU is optional; the system can still run without it.
  Serial.println("[DEBUG] Starting IMU init...");
  if (!imu_init()) {
    Serial.println("[IMU] init failed (continuing without IMU)");
  }
  Serial.println("[DEBUG] IMU init completed");
  Serial.flush();
  
  Serial.println("[DEBUG] Camera init OK");
  Serial.flush();

  // start streaming by default (optional)
  g_streaming = true;
  Serial.println("[SYS] streaming=ON (default). Use UDP cmd stop_stream to stop.");
  Serial.println("[DEBUG] Setup completed successfully!");
  Serial.flush();
}

void loop() {
  // 最初のループでデバッグメッセージを出力（一度だけ）
  static bool first_loop = true;
  if (first_loop) {
    Serial.println("[DEBUG] Entering main loop");
    Serial.flush();
    first_loop = false;
  }
  
  handle_udp_cmd();
  stream_loop_once();

  // keep Wi-Fi alive
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] disconnected, reconnecting...");
    Serial.flush();
    g_streaming = false;
    WiFi.disconnect(true);
    delay(300);
    while (!wifi_connect()) {
      delay(1500);
    }
    g_streaming = true;
  }
}
