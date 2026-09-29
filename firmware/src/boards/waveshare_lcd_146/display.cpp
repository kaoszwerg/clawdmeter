#include "../../hal/display_hal.h"
#include "board.h"
#include <Arduino.h>
#include <Arduino_GFX_Library.h>

// SPD2010 over QSPI. Arduino_GFX's driver carries the same vendor init table
// as Waveshare's esp_lcd_spd2010.c, so it is used as-is. Reset goes through
// the TCA9554 (board_init), hence no reset pin here.
//
// Brightness is a LEDC PWM duty on the backlight — a TFT has no in-panel
// brightness command.

static Arduino_DataBus* bus = nullptr;
static Arduino_SPD2010* gfx = nullptr;

void display_hal_init(void) {
    bus = new Arduino_ESP32QSPI(
        LCD_CS, LCD_SCLK, LCD_SDIO0, LCD_SDIO1, LCD_SDIO2, LCD_SDIO3);
    gfx = new Arduino_SPD2010(bus, GFX_NOT_DEFINED);
}

void display_hal_begin(void) {
    gfx->begin(40000000);   // 40 MHz, as Waveshare's demo
    gfx->fillScreen(0x0000);
    ledcAttach(LCD_BL, 20000 /* Hz, as the demo */, 8 /* bits */);
    ledcWrite(LCD_BL, 200);
}

void display_hal_set_brightness(uint8_t level) {
    ledcWrite(LCD_BL, level);
}

void display_hal_fill_screen(uint16_t color) {
    if (gfx) gfx->fillScreen(color);
}

void display_hal_draw_bitmap(int32_t x, int32_t y, int32_t w, int32_t h,
                             const uint16_t* pixels) {
    if (gfx) gfx->draw16bitRGBBitmap(x, y, (uint16_t*)pixels, w, h);
}

void display_hal_tick(void) {
    // No rotation on this board.
}

// The SPD2010 only accepts column windows that start on a multiple of 4 and
// end on 4N+3 (Waveshare's rounder callback). 412 = 4 x 103, so the widened
// area never leaves the panel.
void display_hal_round_area(int32_t* x1, int32_t* y1, int32_t* x2, int32_t* y2) {
    (void)y1;
    (void)y2;
    *x1 = *x1 & ~3;
    *x2 = *x2 | 3;
}
