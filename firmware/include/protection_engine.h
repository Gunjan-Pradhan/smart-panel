#ifndef PROTECTION_ENGINE_H
#define PROTECTION_ENGINE_H

#include "protection_types.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    ChannelLimits limits;
    ProtectionOutput output;

    // Internal timing state
    uint32_t inrush_timer_ms;
    uint32_t debounce_timer_ms;
    uint32_t retry_timer_ms;
    TripReason pending_trip_reason;

    // Track active fault condition for recovery evaluation
    bool active_voltage_fault;
    bool active_overcurrent_fault;
    bool active_meter_fault;
} ProtectionEngine;

/**
 * Initializes the protection engine with default or configured limits.
 */
void protection_engine_init(ProtectionEngine* engine, const ChannelLimits* limits);

/**
 * Evaluates the effective limits clamped to hard caps.
 */
void protection_engine_get_effective_limits(
    const ProtectionEngine* engine,
    float* effective_current_a,
    float* effective_power_w
);

/**
 * Updates channel limits (e.g. from NVS or user confirmation).
 */
void protection_engine_update_limits(ProtectionEngine* engine, const ChannelLimits* new_limits);

/**
 * Handles incoming relay control commands with strict safety priority.
 */
CommandResult protection_engine_handle_command(
    ProtectionEngine* engine,
    bool turn_on,
    ControlPriority priority,
    CommandReason* out_reason
);

/**
 * Clears lockout state and resets strike counter to 0.
 * Requires authorized manual button or reset command.
 */
void protection_engine_reset_lockout(ProtectionEngine* engine);

/**
 * Cyclic execution step. Call deterministically (e.g. every 10 ms to 100 ms).
 * 
 * @param engine Pointer to protection engine instance
 * @param reading Latest electrical measurements
 * @param dt_ms Milliseconds elapsed since last step call
 */
void protection_engine_step(
    ProtectionEngine* engine,
    const ElectricalReading* reading,
    uint32_t dt_ms
);

/**
 * Returns read-only pointer to current output status.
 */
const ProtectionOutput* protection_engine_get_output(const ProtectionEngine* engine);

#ifdef __cplusplus
}
#endif

#endif // PROTECTION_ENGINE_H

