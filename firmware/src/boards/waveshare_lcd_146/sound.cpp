#include "../../hal/sound_hal.h"

// The speaker hangs off a PCM5101 — a plain I2S DAC with no I2C control
// port — while the shared chime engine drives an ES8311 codec. No chime here
// until someone wires chime.cpp up for a bare DAC.

void sound_hal_init(void) {}
void sound_hal_tick(void) {}
void sound_hal_play_reset(void) {}
void sound_hal_play_pair_armed(void) {}
void sound_hal_play_paired(void) {}
