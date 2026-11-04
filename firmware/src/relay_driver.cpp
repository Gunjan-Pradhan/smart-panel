#include "relay_driver.h"

#ifdef ARDUINO
#include <Arduino.h>
#else
// Stub definitions for host-side native compilation
#define HIGH 1
#define LOW  0
#define OUTPUT 1
static inline void digitalWrite(uint8_t pin, uint8_t val) { (void)pin; (void)val; }
static inline void pinMode(uint8_t pin, uint8_t mode) { (void)pin; (void)mode; }
#endif

void relay_init(RelayChannel* ch, uint8_t pin, bool active_low) {
    if (!ch) return;

    ch->pin = pin;
    ch->active_low = active_low;
    ch->state_is_on = false;

    // SAFE BOOT RULE: Pre-load the OFF level into the GPIO output register
    // BEFORE configuring the pin as an output, eliminating startup contact glitch.
    uint8_t off_level = ch->active_low ? HIGH : LOW;
    digitalWrite(ch->pin, off_level);
    pinMode(ch->pin, OUTPUT);
}

void relay_set(RelayChannel* ch, bool turn_on) {
    if (!ch) return;

    ch->state_is_on = turn_on;
    uint8_t pin_level;

    if (ch->active_low) {
        // Active-LOW: 0 = ON, 1 = OFF
        pin_level = turn_on ? LOW : HIGH;
    } else {
        // Active-HIGH: 1 = ON, 0 = OFF
        pin_level = turn_on ? HIGH : LOW;
    }

    digitalWrite(ch->pin, pin_level);
}

bool relay_get_state(const RelayChannel* ch) {
    return ch ? ch->state_is_on : false;
}

void relay_emergency_all_off(RelayChannel* ch1, RelayChannel* ch2) {
    if (ch1) relay_set(ch1, false);
    if (ch2) relay_set(ch2, false);
}

