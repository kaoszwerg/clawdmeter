#pragma once
#include <lvgl.h>

// Design tokens — single source of truth for UI colors. Anthropic-inspired
// dark palette, AMOLED-friendly (true black bg).
#define THEME_BG       lv_color_hex(0x000000)   // screen background
#define THEME_PANEL    lv_color_hex(0x1f1f1e)   // card/zone fill
#define THEME_TEXT     lv_color_hex(0xfaf9f5)   // primary text
#define THEME_DIM      lv_color_hex(0xb0aea5)   // secondary text
#define THEME_ACCENT   lv_color_hex(0xd97757)   // brand terra-cotta
#define THEME_GREEN    lv_color_hex(0x788c5d)
#define THEME_AMBER    lv_color_hex(0xd97757)
#define THEME_RED      lv_color_hex(0xc0392b)
#define THEME_BAR_BG   lv_color_hex(0x2a2a28)   // unfilled bar track
#define THEME_RING_BG  lv_color_hex(0x4a4945)   // unfilled ring track (round panels) — lighter, so the scale reads

// Weekly-only plans: budget levels of the weekly limit against the elapsed
// share of the week (traffic light, bright enough for the TFTs), and the
// fixed colour of the elapsed gauge — cool, so it never reads as a level.
// Hex values without lv_color_hex() because the pace line uses them as
// LVGL recolor codes too.
#define LEVEL_HEX_UNDER  0x3fb950
#define LEVEL_HEX_ON     0xf2cc0c
#define LEVEL_HEX_OVER   0xff8a00
#define LEVEL_HEX_CRIT   0xff3b30
#define THEME_ELAPSED    lv_color_hex(0x4da3ff)
