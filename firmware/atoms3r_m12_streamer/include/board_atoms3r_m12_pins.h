#pragma once
// AtomS3R-M12 camera pin mapping (OV3660 M12)
// Derived from M5Stack AtomS3R-M12 PinMap.

// SCCB (I2C for camera)
#define CAM_PIN_SIOD 12  // CAM_SDA
#define CAM_PIN_SIOC 9   // CAM_SCL

// Camera data pins
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

// Clock / power-down
#define CAM_PIN_XCLK  21
#define CAM_PIN_PWDN  18  // POWER_N
#define CAM_PIN_RESET -1

// IMU (BMI270) I2C pins (SYS_SDA/SYS_SCL)
// See AtomS3R-M12 PinMap: BMI270 (0x68) uses SYS_SCL/SYS_SDA.
#define IMU_PIN_SCL 0   // SYS_SCL
#define IMU_PIN_SDA 45  // SYS_SDA
