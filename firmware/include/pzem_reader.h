#ifndef PZEM_READER_H
#define PZEM_READER_H

#include <stdint.h>
#include <stdbool.h>
#include "protection_types.h"

#ifdef __cplusplus
extern "C" {
#endif

// Physical AC Plausibility Bounds
#define PZEM_MIN_PLAUSIBLE_VOLTAGE   50.0f
#define PZEM_MAX_PLAUSIBLE_VOLTAGE   300.0f
#define PZEM_MAX_PLAUSIBLE_CURRENT   50.0f
#define PZEM_MIN_PLAUSIBLE_FREQ      40.0f
#define PZEM_MAX_PLAUSIBLE_FREQ      65.0f
#define PZEM_MAX_CURRENT_JUMP        30.0f  // A per sample

typedef struct {
    uint8_t channel;
    uint8_t uart_num;
    uint8_t rx_pin;
    uint8_t tx_pin;
    uint8_t modbus_addr;

    ElectricalReading last_reading;
    bool has_previous_sample;
    float previous_current_a;

    // Simulation / Injection Override
    bool injection_active;
    ElectricalReading injected_reading;
} PZEMReader;

void pzem_reader_init(
    PZEMReader* reader,
    uint8_t channel,
    uint8_t uart_num,
    uint8_t rx_pin,
    uint8_t tx_pin,
    uint8_t modbus_addr
);

/**
 * Validates a parsed reading against physical plausibility laws.
 */
bool pzem_validate_reading(const ElectricalReading* r, float prev_current_a, bool has_prev);

/**
 * Polls the PZEM meter non-blockingly or yields active injected readings.
 */
bool pzem_poll_reading(PZEMReader* reader, ElectricalReading* out_reading);

/**
 * Injects synthetic electrical readings for safe laboratory testing without mains.
 */
void pzem_inject_fault(
    PZEMReader* reader,
    float v, float i, float p, float pf, float f, bool valid
);

/**
 * Clears fault injection override, returning to live hardware polling.
 */
void pzem_clear_injection(PZEMReader* reader);

/**
 * Calculates standard Modbus RTU CRC16 checksum.
 */
uint16_t pzem_calculate_crc16(const uint8_t *buffer, uint16_t len);

#ifdef __cplusplus
}
#endif

#endif // PZEM_READER_H

