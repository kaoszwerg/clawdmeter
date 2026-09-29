#include "../../hal/touch_hal.h"
#include "board.h"
#include <Arduino.h>
#include <Wire.h>

// SPD2010 touch half, ported from Waveshare's Touch_SPD2010.cpp. Unlike the
// FocalTech-style chips on the other ports, it has 16-bit register addresses
// and a small state machine: after reset the controller sits in its BIOS and
// has to be told to start its CPU, then to switch to point mode and start
// scanning, and every report has to be acknowledged by clearing its INT.
//
// A read runs only while INT is low (data pending) or a finger is down. The
// controller reports continuously while touched, so a finger that sends no
// report for TOUCH_RELEASE_MS counts as lifted, in case the lift report is
// lost. Coordinates are panel-native; no swap or mirror.

#define TOUCH_RELEASE_MS 120

static volatile bool touch_irq = false;
static bool     touch_pressed = false;
static uint16_t touch_x = 0;
static uint16_t touch_y = 0;
static uint32_t last_report_ms = 0;

static void IRAM_ATTR touch_isr(void) {
    touch_irq = true;
}

static bool tp_write(uint16_t reg, uint8_t d0, uint8_t d1) {
    Wire.beginTransmission(SPD2010_TP_ADDR);
    Wire.write((uint8_t)(reg >> 8));
    Wire.write((uint8_t)reg);
    Wire.write(d0);
    Wire.write(d1);
    bool ok = Wire.endTransmission() == 0;
    delayMicroseconds(200);
    return ok;
}

static bool tp_read(uint16_t reg, uint8_t* buf, uint8_t len) {
    Wire.beginTransmission(SPD2010_TP_ADDR);
    Wire.write((uint8_t)(reg >> 8));
    Wire.write((uint8_t)reg);
    if (Wire.endTransmission() != 0) return false;
    if (Wire.requestFrom((uint8_t)SPD2010_TP_ADDR, len) != len) return false;
    for (uint8_t i = 0; i < len; i++) buf[i] = Wire.read();
    return true;
}

static void tp_clear_int(void)  { tp_write(0x0200, 0x01, 0x00); }
static void tp_cpu_start(void)  { tp_write(0x0400, 0x01, 0x00); }
static void tp_point_mode(void) { tp_write(0x5000, 0x00, 0x00); }
static void tp_start(void)      { tp_write(0x4600, 0x00, 0x00); }

// One pass of Waveshare's tp_read_data(). Returns true when a point report
// was read; *fingers / *x / *y / *weight then hold its first point.
static bool tp_poll(uint8_t* fingers, uint16_t* x, uint16_t* y, uint8_t* weight) {
    uint8_t st[4];
    if (!tp_read(0x2000, st, 4)) return false;
    delayMicroseconds(200);
    bool pt_exist    = st[0] & 0x01;
    bool gesture     = st[0] & 0x02;
    bool aux         = st[0] & 0x08;
    bool tic_in_bios = st[1] & 0x40;
    bool tic_in_cpu  = st[1] & 0x20;
    bool cpu_run     = st[1] & 0x08;
    uint16_t read_len = (uint16_t)st[3] << 8 | st[2];

    if (tic_in_bios) {
        tp_clear_int();
        tp_cpu_start();
        return false;
    }
    if (tic_in_cpu) {
        tp_point_mode();
        tp_start();
        tp_clear_int();
        return false;
    }
    if (cpu_run && read_len == 0) {
        tp_clear_int();
        return false;
    }
    if (!(pt_exist || gesture)) {
        if (cpu_run && aux) tp_clear_int();
        return false;
    }

    // HDP packet: 4-byte header + 6 bytes per finger (at most 10).
    uint8_t hdp[4 + 10 * 6];
    if (read_len > sizeof(hdp)) read_len = sizeof(hdp);
    bool got_points = false;
    if (read_len >= 4 && tp_read(0x0003, hdp, (uint8_t)read_len)) {
        uint8_t id = hdp[4];
        if (pt_exist && id <= 0x0A && read_len >= 10) {
            *fingers = (read_len - 4) / 6;
            *x = (uint16_t)(hdp[7] & 0xF0) << 4 | hdp[5];
            *y = (uint16_t)(hdp[7] & 0x0F) << 8 | hdp[6];
            *weight = hdp[8];
            got_points = true;
        }
    }

    // Drain the packet and acknowledge it (HDP status 0x82 = done,
    // 0x00 = more data to read first).
    for (int i = 0; i < 8; i++) {
        uint8_t hs[8];
        if (!tp_read(0xFC02, hs, 8)) break;
        if (hs[5] == 0x82) { tp_clear_int(); break; }
        if (hs[5] != 0x00) break;
        uint16_t remain = (uint16_t)hs[3] << 8 | hs[2];
        uint8_t junk[32];
        if (remain > sizeof(junk)) remain = sizeof(junk);
        if (remain == 0 || !tp_read(0x0003, junk, (uint8_t)remain)) break;
    }
    return got_points;
}

void touch_hal_init(void) {
    // Reset was pulsed through the TCA9554 in board_init(). Firmware version
    // block at 0x2600 carries the IC name ("SPD" / "2010") — a cheap probe.
    uint8_t fw[18];
    if (tp_read(0x2600, fw, sizeof(fw))) {
        Serial.printf("Touch SPD2010 fw ver=%u (addr 0x%02X)\n",
                      (unsigned)(fw[5] << 8 | fw[4]), SPD2010_TP_ADDR);
    } else {
        Serial.printf("Touch SPD2010 probe failed (addr 0x%02X)\n", SPD2010_TP_ADDR);
    }

    pinMode(TP_INT, INPUT_PULLUP);
    attachInterrupt(TP_INT, touch_isr, FALLING);
}

void touch_hal_read(uint16_t* x, uint16_t* y, bool* pressed) {
    bool pending = touch_irq || digitalRead(TP_INT) == LOW;
    if (pending || touch_pressed) {
        touch_irq = false;
        uint8_t fingers = 0, weight = 0;
        uint16_t px = 0, py = 0;
        if (tp_poll(&fingers, &px, &py, &weight)) {
            if (fingers > 0 && weight > 0) {
                if (px >= LCD_WIDTH)  px = LCD_WIDTH - 1;
                if (py >= LCD_HEIGHT) py = LCD_HEIGHT - 1;
                touch_x = px;
                touch_y = py;
                touch_pressed = true;
                last_report_ms = millis();
            } else {
                touch_pressed = false;   // lift report (weight 0)
            }
        } else if (touch_pressed && millis() - last_report_ms > TOUCH_RELEASE_MS) {
            touch_pressed = false;
        }
    }
    *x = touch_x;
    *y = touch_y;
    *pressed = touch_pressed;
}
