#ifndef PANEL_CONFIG_H
#define PANEL_CONFIG_H

#include <stdint.h>
#include <stdbool.h>

// Device Identification per docs/mqtt_contract.md §2
#define DEFAULT_DEVICE_ID "PANEL-0001"
#define FIRMWARE_VERSION  "1.0.0"

// Hardware Pinout Mapping per docs/hardware_notes.md
// Channel 1: Industrial Load (Induction Motor)
#define CH1_NAME                "CH1_MOTOR"
#define CH1_UART_NUM            2
#define CH1_RX_PIN              4
#define CH1_TX_PIN              5
#define CH1_RELAY_PIN           6
#define CH1_RELAY_ACTIVE_LOW    true    // Active-LOW relay module (0 = ON, 1 = OFF)
#define CH1_INRUSH_BLANKING_MS  2000    // 2.0 s motor inrush window

// Channel 2: Household Load (Resistive Bulbs)
#define CH2_NAME                "CH2_BULBS"
#define CH2_UART_NUM            1
#define CH2_RX_PIN              44
#define CH2_TX_PIN              43
#define CH2_RELAY_PIN           38
#define CH2_RELAY_ACTIVE_LOW    false   // Active-HIGH SSR-40DA (1 = ON, 0 = OFF)
#define CH2_INRUSH_BLANKING_MS  50      // 50 ms cold-filament window

// User Interface Peripherals (LEDs and Buttons)
#define PIN_LED_SYSTEM          10
#define PIN_LED_CH1             11
#define PIN_LED_CH2             12
#define PIN_BTN_LEARN           13
#define PIN_BTN_RESET           14

// Telemetry Timing Constants
#define TELEMETRY_INTERVAL_MS   1000    // 1 Hz publication
#define HEARTBEAT_INTERVAL_MS   60000   // 60 s heartbeat
#define WATCHDOG_TIMEOUT_S      10      // 10 s hardware watchdog

// Default Wi-Fi & MQTT Configuration
#define DEFAULT_WIFI_SSID       "SmartPanel_AP"
#define DEFAULT_WIFI_PASS       "protection2026"
#define DEFAULT_MQTT_HOST       "127.0.0.1"
#define DEFAULT_MQTT_PORT       1883

#endif // PANEL_CONFIG_H

