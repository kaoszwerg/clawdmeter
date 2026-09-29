#include "../../hal/imu_hal.h"

// QMI8658 is populated but unused — the round panel has no preferred
// orientation to rotate into.

void    imu_hal_init(void) {}
void    imu_hal_tick(void) {}
uint8_t imu_hal_rotation_quadrant(void) { return 0; }
