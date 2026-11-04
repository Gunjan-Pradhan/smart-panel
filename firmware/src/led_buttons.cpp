#include "led_buttons.h"
#include "panel_config.h"

#ifdef ARDUINO
#include <Arduino.h>
#else
#define INPUT_PULLUP 2
#define OUTPUT 1
#define HIGH 1
#define LOW 0
static inline void pinMode(uint8_t pin, uint8_t mode) { (void)pin; (void)mode; }
static inline void digitalWrite(uint8_t pin, uint8_t val) { (void)pin; (void)val; }
static inline int digitalRead(uint8_t pin) { (void)pin; return 1; }
#endif

static uint32_t last_btn1_change = 0;
static uint32_t last_btn2_change = 0;
static bool btn1_last_state = true;
static bool btn2_last_state = true;

void ui_peripherals_init(void) {
    pinMode(PIN_LED_SYSTEM, OUTPUT);
    pinMode(PIN_LED_CH1, OUTPUT);
    pinMode(PIN_LED_CH2, OUTPUT);

    digitalWrite(PIN_LED_SYSTEM, LOW);
    digitalWrite(PIN_LED_CH1, LOW);
    digitalWrite(PIN_LED_CH2, LOW);

    pinMode(PIN_BTN_LEARN, INPUT_PULLUP);
    pinMode(PIN_BTN_RESET, INPUT_PULLUP);
}

static uint8_t get_channel_led_level(ChannelState state, uint32_t now_ms) {
    switch (state) {
        case STATE_OFF:
            return LOW;
        case STATE_RUNNING:
            return HIGH;
        case STATE_INRUSH:
            // Fast toggle (100 ms)
            return ((now_ms / 100) % 2 == 0) ? HIGH : LOW;
        case STATE_FAULT_RETRY:
        case STATE_LOCKOUT:
        case STATE_METER_LOST:
            // Slower fault blink (500 ms)
            return ((now_ms / 500) % 2 == 0) ? HIGH : LOW;
        default:
            return LOW;
    }
}

void ui_update_leds(
    bool wifi_connected,
    ChannelState ch1_state,
    ChannelState ch2_state,
    uint32_t now_ms
) {
    // System Wi-Fi LED
    if (wifi_connected) {
        digitalWrite(PIN_LED_SYSTEM, HIGH);
    } else {
        // Connecting blink (1 Hz)
        digitalWrite(PIN_LED_SYSTEM, ((now_ms / 1000) % 2 == 0) ? HIGH : LOW);
    }

    // Channel LEDs
    digitalWrite(PIN_LED_CH1, get_channel_led_level(ch1_state, now_ms));
    digitalWrite(PIN_LED_CH2, get_channel_led_level(ch2_state, now_ms));
}

ButtonEvents ui_poll_buttons(uint32_t now_ms) {
    ButtonEvents ev = { false, false };

    // Debounce button 1 (Learn Mode)
    bool b1 = (digitalRead(PIN_BTN_LEARN) == LOW);
    if (b1 != btn1_last_state && (now_ms - last_btn1_change > 50)) {
        last_btn1_change = now_ms;
        btn1_last_state = b1;
        if (b1) ev.btn_learn_pressed = true;
    }

    // Debounce button 2 (Reset / Lockout Clear)
    bool b2 = (digitalRead(PIN_BTN_RESET) == LOW);
    if (b2 != btn2_last_state && (now_ms - last_btn2_change > 50)) {
        last_btn2_change = now_ms;
        btn2_last_state = b2;
        if (b2) ev.btn_reset_pressed = true;
    }

    return ev;
}

