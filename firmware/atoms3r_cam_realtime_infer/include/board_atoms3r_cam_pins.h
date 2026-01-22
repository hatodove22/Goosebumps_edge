#pragma once
// AtomS3R-CAM (GC0308) pin mapping
// Source: M5Stack AtomS3R-CAM PinMap (docs.m5stack.com)

// Camera SCCB (I2C for sensor)
#define CAM_PIN_SIOD 12  // CAM_SDA
#define CAM_PIN_SIOC 9   // CAM_SCL

// Camera data pins (Y2..Y9)
#define CAM_PIN_D0 3   // Y2
#define CAM_PIN_D1 42  // Y3
#define CAM_PIN_D2 46  // Y4
#define CAM_PIN_D3 48  // Y5
#define CAM_PIN_D4 4   // Y6
#define CAM_PIN_D5 17  // Y7
#define CAM_PIN_D6 11  // Y8
#define CAM_PIN_D7 13  // Y9

// Sync pins
#define CAM_PIN_VSYNC 10
#define CAM_PIN_HREF  14
#define CAM_PIN_PCLK  40

// Clock / power / reset
#define CAM_PIN_XCLK  21
#define CAM_PIN_POWER_N 18   // POWER_N (active-low enable)
#define CAM_PIN_RESET -1

// IMU (BMI270) I2C pins (SYS_SCL/SYS_SDA)
#define IMU_PIN_SCL 0
#define IMU_PIN_SDA 45

// IR LED driver pin (optional)
#define IR_LED_DRV_PIN 47
