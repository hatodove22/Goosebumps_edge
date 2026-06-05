#pragma once

// Seeed Studio XIAO ESP32S3 Sense camera slot pin map.
// Source: Seeed Studio XIAO ESP32S3 Sense camera documentation.
//
// GPIO10 XMCLK, GPIO13 PCLK, GPIO38 VSYNC, GPIO47 HREF
// GPIO39 CAM_SCL, GPIO40 CAM_SDA
// GPIO15 Y2, GPIO17 Y3, GPIO18 Y4, GPIO16 Y5
// GPIO14 Y6, GPIO12 Y7, GPIO11 Y8, GPIO48 Y9

#define CAM_PIN_PWDN  -1
#define CAM_PIN_RESET -1

#define CAM_PIN_XCLK  10
#define CAM_PIN_SIOD  40
#define CAM_PIN_SIOC  39

#define CAM_PIN_D0    15
#define CAM_PIN_D1    17
#define CAM_PIN_D2    18
#define CAM_PIN_D3    16
#define CAM_PIN_D4    14
#define CAM_PIN_D5    12
#define CAM_PIN_D6    11
#define CAM_PIN_D7    48

#define CAM_PIN_VSYNC 38
#define CAM_PIN_HREF  47
#define CAM_PIN_PCLK  13
