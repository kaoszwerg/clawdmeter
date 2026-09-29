#include "../../hal/power_hal.h"
#include "../../hal/display_hal.h"
#include "board.h"
#include <Arduino.h>
#include <driver/gpio.h>
#include <esp_sleep.h>

// No PMU on this kit. Battery percentage comes from the VBAT divider on
// BAT_ADC_PIN; no charger status line reaches a GPIO, and VBUS isn't sensed
// either, so is_charging / is_vbus_in stay false.
//
// PWR is a plain active-LOW GPIO (it also powers the board on while pressed).
// Same software edge synthesis as the LCD-1.54 port:
//   short    — fired on release if the hold was shorter than PWR_LONG_MS
//   long     — fired once when a hold crosses PWR_LONG_MS
//   release  — fired on every release edge
// Holding PWR to 8 s drops the power latch (hard off on battery) and deep-
// sleeps (pseudo-off on USB, woken by the PWR key). The pairing gesture in
// main.cpp disarms at 6 s, so the timings compose.
//
// The very first PWR press after power-up is the one that switched the board
// on; its release is swallowed so it doesn't also cycle the screen.

#define BATTERY_POLL_MS  2000
#define PWR_POLL_MS      50
#define PWR_LONG_MS      1500
#define PWR_OFF_HOLD_MS  8000   // mirrors the AXP2101 PKEY 8s shutdown

static int      cached_pct        = -1;
static bool     pwr_pressed_flag  = false;
static bool     pwr_long_flag     = false;
static bool     pwr_released_flag = false;
static bool     last_pwr_state    = false;
static bool     power_on_hold     = false;
static uint32_t pwr_press_started_ms = 0;
static bool     pwr_long_fired    = false;
static uint32_t last_battery_ms   = 0;
static uint32_t last_pwr_ms       = 0;

static void sample_battery(void) {
    // Average a few reads — the divider is high-impedance and single ADC
    // samples on the S3 are noisy.
    uint32_t mv = 0;
    for (int i = 0; i < 4; i++) mv += analogReadMilliVolts(BAT_ADC_PIN);
    float vbat = (mv / 4) * BAT_VOLT_DIVIDER / 1000.0f;

    if (vbat < 3.0f) {          // divider floating — no battery connected
        cached_pct = -1;
        return;
    }
    // Linear 3.3 V → 0%, 4.2 V → 100%. Crude but serviceable for a
    // four-state indicator icon.
    int pct = (int)((vbat - 3.3f) * (100.0f / 0.9f) + 0.5f);
    cached_pct = pct < 0 ? 0 : pct > 100 ? 100 : pct;
}

static void power_off(void) {
    Serial.println("PWR held 8s — powering off");
    Serial.flush();
    display_hal_set_brightness(0);
    delay(50);

    // Drop the power latch and keep it low through deep sleep. On battery
    // this cuts the rail as soon as the key is released; on USB the chip
    // deep-sleeps until the PWR key (RTC-capable GPIO) is pressed again.
    digitalWrite(PWR_LATCH, LOW);
    gpio_hold_en((gpio_num_t)PWR_LATCH);
    esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH, ESP_PD_OPTION_ON);
    // Wait for the release first, or the still-held key wakes us at once.
    while (digitalRead(BTN_PWR_GPIO) == LOW) delay(10);
    delay(100);
    esp_sleep_enable_ext0_wakeup((gpio_num_t)BTN_PWR_GPIO, 0);
    esp_deep_sleep_start();
}

void power_hal_init(void) {
    pinMode(BTN_PWR_GPIO, INPUT_PULLUP);
    analogReadResolution(12);
    sample_battery();
    power_on_hold = (digitalRead(BTN_PWR_GPIO) == LOW);
    last_pwr_state = power_on_hold;
}

void power_hal_tick(void) {
    uint32_t now = millis();

    if (now - last_battery_ms >= BATTERY_POLL_MS) {
        last_battery_ms = now;
        sample_battery();
    }
    if (now - last_pwr_ms >= PWR_POLL_MS) {
        last_pwr_ms = now;
        bool pwr_now = (digitalRead(BTN_PWR_GPIO) == LOW);   // active LOW
        if (power_on_hold) {
            if (!pwr_now) power_on_hold = false;              // swallow it
        } else if (pwr_now && !last_pwr_state) {     // press edge — hold begins
            pwr_press_started_ms = now;
            pwr_long_fired = false;
        } else if (pwr_now && last_pwr_state) {      // held
            if (!pwr_long_fired && (now - pwr_press_started_ms >= PWR_LONG_MS)) {
                pwr_long_flag  = true;
                pwr_long_fired = true;
            }
            if (now - pwr_press_started_ms >= PWR_OFF_HOLD_MS) {
                power_off();   // does not return
            }
        } else if (!pwr_now && last_pwr_state) {     // release edge
            pwr_released_flag = true;
            if (!pwr_long_fired) pwr_pressed_flag = true;  // short press
        }
        last_pwr_state = pwr_now;
    }
}

int  power_hal_battery_pct(void) { return cached_pct; }
bool power_hal_is_charging(void) { return false; }
bool power_hal_is_vbus_in(void)  { return false; }

bool power_hal_pwr_pressed(void) {
    if (pwr_pressed_flag) { pwr_pressed_flag = false; return true; }
    return false;
}

bool power_hal_pwr_long_pressed(void) {
    if (pwr_long_flag) { pwr_long_flag = false; return true; }
    return false;
}

bool power_hal_pwr_released(void) {
    if (pwr_released_flag) { pwr_released_flag = false; return true; }
    return false;
}
