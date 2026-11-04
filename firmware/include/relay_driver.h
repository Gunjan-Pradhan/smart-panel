#ifndef RELAY_DRIVER_H
#define RELAY_DRIVER_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint8_t pin;
    bool active_low;
    bool state_is_on;
} RelayChannel;

/**
 * Initializes a relay channel safely with glitch prevention at boot.
 * Writes the OFF logic level BEFORE setting the pin mode to OUTPUT.
 */
void relay_init(RelayChannel* ch, uint8_t pin, bool active_low);

/**
 * Actuates the relay respecting configured polarity.
 */
void relay_set(RelayChannel* ch, bool turn_on);

/**
 * Returns current commanded relay state (true = ON, false = OFF).
 */
bool relay_get_state(const RelayChannel* ch);

/**
 * Emergency shutoff of both channels.
 */
void relay_emergency_all_off(RelayChannel* ch1, RelayChannel* ch2);

#ifdef __cplusplus
}
#endif

#endif // RELAY_DRIVER_H

