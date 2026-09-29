#pragma once

// Waveshare ESP32-S3-Touch-LCD-1.46 / 1.46B — round 1.46" IPS TFT. The two
// differ only in the cover glass. 412x412 SPD2010 over QSPI; the same chip is
// also the touch controller (I2C 0x53). TCA9554 IO expander gates the LCD and
// touch resets. No PMU: a GPIO power latch keeps the board alive on battery,
// and battery voltage comes from an ADC divider. PCM5101 DAC + speaker,
// QMI8658 IMU and PCF85063 RTC are populated but unused.
//
// Pin map from Waveshare's demo package (Arduino/examples/LVGL_Arduino and
// ESP-IDF/ESP32-S3-Touch-LCD-1.46-Test) checked against the schematic
// (nets Key_BAT, BAT_Control, BAT_ADC).

#define BOARD_NAME           "Waveshare LCD 1.46"

// ---- Display geometry ----
// Round panel: the full 412x412 frame is addressable, only the inscribed
// circle is visible (BoardCaps.is_round tells the UI).
#define LCD_WIDTH            412
#define LCD_HEIGHT           412

// ---- QSPI display pins (SPD2010) ----
#define LCD_CS               21
#define LCD_SCLK             40
#define LCD_SDIO0            46
#define LCD_SDIO1            45
#define LCD_SDIO2            42
#define LCD_SDIO3            41
#define LCD_BL               5     // backlight, LEDC PWM (HIGH = on)
// LCD reset is TCA9554 EXIO2, pulsed in board_init().

// ---- I2C bus (touch, IO expander, IMU, RTC share one bus) ----
#define IIC_SDA              11
#define IIC_SCL              10

// ---- IO expander (TCA9554) ----
// EXIOn is bit n-1. All pins are outputs; the resets are active LOW.
#define TCA9554_ADDR         0x20
#define EXIO_TP_RST          0     // EXIO1
#define EXIO_LCD_RST         1     // EXIO2
#define EXIO_SD_CS           2     // EXIO3

// ---- Touch (SPD2010 touch half, 16-bit register addresses) ----
#define TP_INT               4
#define SPD2010_TP_ADDR      0x53

// ---- Power (no PMU) ----
// PWR_LATCH (BAT_Control) holds the battery rail on: the PWR key only powers
// the board while it is pressed, so firmware must drive this HIGH early or a
// battery-powered board dies as soon as the key is released. PWR_KEY
// (Key_BAT) reads the same key, LOW while pressed.
#define PWR_LATCH            7
#define BTN_PWR_GPIO         6
#define BAT_ADC_PIN          8
// 3:1 divider; Waveshare's demo also divides by a 0.990476 calibration trim.
#define BAT_VOLT_DIVIDER     (3.0f / 0.990476f)

// ---- Buttons (active-LOW GPIOs) ----
#define BTN_BACK_GPIO        0     // BOOT — primary, Space (PTT)

// ---- Capability flags ----
#define BOARD_HAS_SECONDARY_BUTTON 0
#define BOARD_HAS_ROTATION         0
#define BOARD_HAS_IMU              0    // QMI8658 present but unused
#define BOARD_HAS_BATTERY          1
#define BOARD_HAS_IO_EXPANDER      1
// PCM5101 is a plain I2S DAC, not the ES8311 the shared chime engine drives.
#define BOARD_HAS_SOUND            0
