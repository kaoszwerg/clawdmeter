#include "board.h"
#include <Arduino.h>
#include <Wire.h>
#include <driver/gpio.h>

// The Arduino core calls initVariant() before setup(), i.e. before the
// Serial.begin() delay in main.cpp. Raising the power latch here keeps the
// PWR press that is needed to switch on from battery as short as possible.
extern "C" void initVariant(void) {
    // Release the pad hold a power-off left behind (power.cpp holds the latch
    // LOW through deep sleep), otherwise the HIGH write would not reach the pin.
    gpio_hold_dis((gpio_num_t)PWR_LATCH);
    pinMode(PWR_LATCH, OUTPUT);
    digitalWrite(PWR_LATCH, HIGH);
}

static void tca_write(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(TCA9554_ADDR);
    Wire.write(reg);
    Wire.write(val);
    if (Wire.endTransmission() != 0) {
        Serial.printf("TCA9554 write reg %u failed\n", reg);
    }
}

// Bring up the shared I2C bus and release the display and touch from reset
// via the TCA9554. Must run before display_hal_init()/touch_hal_init(), or
// the SPD2010 stays in reset and neither half answers.
extern "C" void board_init(void) {
    Wire.begin(IIC_SDA, IIC_SCL, 400000);

    const uint8_t idle = 0xFF;   // every EXIO HIGH: resets released, SD deselected
    const uint8_t in_reset = idle & ~((1 << EXIO_LCD_RST) | (1 << EXIO_TP_RST));
    tca_write(0x01, idle);       // output register first, so no glitch
    tca_write(0x03, 0x00);       // configuration: all outputs
    tca_write(0x01, in_reset);
    delay(50);
    tca_write(0x01, idle);
    delay(120);
}
