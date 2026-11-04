#ifndef LED_BUTTONS_H
#define LED_BUTTONS_H

#include <stdbool.h>
#include <stdint.h>
#include "protection_types.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    bool btn_learn_pressed;
    bool btn_reset_pressed;
} ButtonEvents;

void ui_peripherals_init(void);
void ui_update_leds(
    bool wifi_connected,
    ChannelState ch1_state,
    ChannelState ch2_state,
    uint32_t now_ms
);
ButtonEvents ui_poll_buttons(uint32_t now_ms);

#ifdef __cplusplus
}
#endif

#endif // LED_BUTTONS_H

