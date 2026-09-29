#pragma once

// Which animation set the firmware carries, chosen at build time.
//
//   (default)            splash_animations.h         claudepix Clawd, 20x20, 10 colours
//   -DSPLASH_SET_MONKEY  splash_animations_monkey.h  the Professor, 40x40, 16 colours
//
// Every set provides the same things — splash_anim_def_t, splash_anims[],
// SPLASH_ANIM_COUNT, SPLASH_PALETTE_SIZE — and may define SPLASH_GRID (20
// when it doesn't). Animations are looked up by name, so a set that uses the
// stock names (idle breathe, work coding, allow, …) works with the rotation
// groups in splash.cpp and with host-named animations unchanged; a name a set
// lacks is simply skipped.
//
// Any board, from the command line:
//   PLATFORMIO_BUILD_FLAGS=-DSPLASH_SET_MONKEY pio run -d firmware -e <env>
#if defined(SPLASH_SET_MONKEY)
#include "splash_animations_monkey.h"
#else
#include "splash_animations.h"
#endif
