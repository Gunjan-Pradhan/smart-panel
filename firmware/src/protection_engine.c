#include "protection_engine.h"

void protection_engine_init(ProtectionEngine* engine, const ChannelLimits* limits) {
    if (!engine) return;

    if (limits) {
        engine->limits = *limits;
    } else {
        // Safe hardcoded defaults
        engine->limits.hard_max_voltage_v = 275.0f;
        engine->limits.hard_min_voltage_v = 175.0f;
        engine->limits.hard_max_current_a = 16.0f;
        engine->limits.hard_max_power_w = 3600.0f;
        engine->limits.hard_min_frequency_hz = 45.0f;
        engine->limits.hard_max_frequency_hz = 65.0f;

        engine->limits.confirmed_current_a = 0.0f;
        engine->limits.confirmed_power_w = 0.0f;
        engine->limits.confirmed_min_pf = 0.0f;

        engine->limits.inrush_blanking_ms = 2000;
        engine->limits.trip_debounce_ms = 150;
        engine->limits.retry_delay_ms = 10000;
        engine->limits.max_retry_strikes = 3;
        engine->limits.meter_fail_limit = 5;

        engine->limits.voltage_hysteresis_v = 5.0f;
        engine->limits.current_hysteresis_a = 0.10f;
    }

    // Output initialization: Safe boot OFF
    engine->output.state = STATE_OFF;
    engine->output.relay_commanded = false;
    engine->output.last_trip_reason = TRIP_NONE;
    engine->output.strike_count = 0;
    engine->output.inrush_active = false;
    engine->output.remaining_retry_ms = 0;
    engine->output.consecutive_meter_fails = 0;

    engine->inrush_timer_ms = 0;
    engine->debounce_timer_ms = 0;
    engine->retry_timer_ms = 0;
    engine->pending_trip_reason = TRIP_NONE;

    engine->active_voltage_fault = false;
    engine->active_overcurrent_fault = false;
    engine->active_meter_fault = false;
}

void protection_engine_get_effective_limits(
    const ProtectionEngine* engine,
    float* effective_current_a,
    float* effective_power_w
) {
    if (!engine) return;

    // The effective limit is MIN(confirmed_limit, hard_cap).
    // Unconfirmed limits (<= 0) default to the hard cap.
    if (effective_current_a) {
        if (engine->limits.confirmed_current_a > 0.0f &&
            engine->limits.confirmed_current_a < engine->limits.hard_max_current_a) {
            *effective_current_a = engine->limits.confirmed_current_a;
        } else {
            *effective_current_a = engine->limits.hard_max_current_a;
        }
    }

    if (effective_power_w) {
        if (engine->limits.confirmed_power_w > 0.0f &&
            engine->limits.confirmed_power_w < engine->limits.hard_max_power_w) {
            *effective_power_w = engine->limits.confirmed_power_w;
        } else {
            *effective_power_w = engine->limits.hard_max_power_w;
        }
    }
}

void protection_engine_update_limits(ProtectionEngine* engine, const ChannelLimits* new_limits) {
    if (!engine || !new_limits) return;

    // Copy over limits while protecting hard caps
    float saved_hard_max_v = engine->limits.hard_max_voltage_v;
    float saved_hard_min_v = engine->limits.hard_min_voltage_v;
    float saved_hard_max_i = engine->limits.hard_max_current_a;
    float saved_hard_max_p = engine->limits.hard_max_power_w;

    engine->limits = *new_limits;

    // Restore invariant hard caps
    engine->limits.hard_max_voltage_v = saved_hard_max_v;
    engine->limits.hard_min_voltage_v = saved_hard_min_v;
    engine->limits.hard_max_current_a = saved_hard_max_i;
    engine->limits.hard_max_power_w = saved_hard_max_p;
}

CommandResult protection_engine_handle_command(
    ProtectionEngine* engine,
    bool turn_on,
    ControlPriority priority,
    CommandReason* out_reason
) {
    if (!engine) {
        if (out_reason) *out_reason = CMD_REASON_INTERNAL_ERROR;
        return CMD_RESULT_FAILED;
    }

    if (turn_on) {
        // Refusal Checks:
        // 1. Safety lockout active
        if (engine->output.state == STATE_LOCKOUT) {
            if (out_reason) *out_reason = CMD_REASON_SAFETY_LOCKOUT;
            return CMD_RESULT_REJECTED;
        }

        // 2. Meter fault active
        if (engine->output.state == STATE_METER_LOST || engine->active_meter_fault) {
            if (out_reason) *out_reason = CMD_REASON_METER_FAULT;
            return CMD_RESULT_REJECTED;
        }

        // 3. Active voltage fault (grid unusable)
        if (engine->active_voltage_fault) {
            if (out_reason) *out_reason = CMD_REASON_ACTIVE_FAULT;
            return CMD_RESULT_REJECTED;
        }

        // Priority check: Advisory signals cannot turn on a relay
        if (priority > PRIORITY_OPTIMIZATION) {
            if (out_reason) *out_reason = CMD_REASON_SAFETY_LOCKOUT;
            return CMD_RESULT_REJECTED;
        }

        // Accept command: Start inrush blanking state
        engine->output.state = STATE_INRUSH;
        engine->output.relay_commanded = true;
        engine->output.inrush_active = true;
        engine->inrush_timer_ms = engine->limits.inrush_blanking_ms;
        engine->debounce_timer_ms = 0;
        engine->retry_timer_ms = 0;
        engine->output.remaining_retry_ms = 0;

        if (out_reason) *out_reason = CMD_REASON_OK;
        return CMD_RESULT_DONE;
    } else {
        // Turning OFF is always permitted regardless of priority or state
        engine->output.state = STATE_OFF;
        engine->output.relay_commanded = false;
        engine->output.inrush_active = false;
        engine->inrush_timer_ms = 0;
        engine->debounce_timer_ms = 0;
        engine->retry_timer_ms = 0;
        engine->output.remaining_retry_ms = 0;
        engine->output.last_trip_reason = TRIP_MANUAL_OFF;

        if (out_reason) *out_reason = CMD_REASON_OK;
        return CMD_RESULT_DONE;
    }
}

void protection_engine_reset_lockout(ProtectionEngine* engine) {
    if (!engine) return;

    engine->output.state = STATE_OFF;
    engine->output.relay_commanded = false;
    engine->output.strike_count = 0;
    engine->output.last_trip_reason = TRIP_NONE;
    engine->output.inrush_active = false;
    engine->output.remaining_retry_ms = 0;
    engine->debounce_timer_ms = 0;
    engine->retry_timer_ms = 0;
}

void protection_engine_step(
    ProtectionEngine* engine,
    const ElectricalReading* reading,
    uint32_t dt_ms
) {
    if (!engine) return;

    // --- 1. METER COMMUNICATION CHECK ---
    if (!reading || !reading->valid) {
        engine->output.consecutive_meter_fails++;
        if (engine->output.consecutive_meter_fails >= engine->limits.meter_fail_limit) {
            engine->active_meter_fault = true;
            if (engine->output.state != STATE_LOCKOUT) {
                engine->output.state = STATE_METER_LOST;
                engine->output.relay_commanded = false;
                engine->output.inrush_active = false;
                engine->output.last_trip_reason = TRIP_METER_LOST;
            }
            return;
        }
    } else {
        engine->output.consecutive_meter_fails = 0;
        engine->active_meter_fault = false;
        // If recovered from meter lost and relay is commanded off, return to STATE_OFF
        if (engine->output.state == STATE_METER_LOST) {
            engine->output.state = STATE_OFF;
            engine->output.relay_commanded = false;
        }
    }

    if (!reading || !reading->valid) return;

    // --- 2. GRID VOLTAGE BASELINE CHECK ---
    // Track active voltage fault (used for re-arming / command rejection)
    if (reading->voltage_v > engine->limits.hard_max_voltage_v ||
        reading->voltage_v < engine->limits.hard_min_voltage_v) {
        engine->active_voltage_fault = true;
    } else if (reading->voltage_v <= (engine->limits.hard_max_voltage_v - engine->limits.voltage_hysteresis_v) &&
               reading->voltage_v >= (engine->limits.hard_min_voltage_v + engine->limits.voltage_hysteresis_v)) {
        engine->active_voltage_fault = false;
    }

    // Determine effective operating limits
    float eff_current_a = engine->limits.hard_max_current_a;
    float eff_power_w = engine->limits.hard_max_power_w;
    protection_engine_get_effective_limits(engine, &eff_current_a, &eff_power_w);

    // --- 3. STATE MACHINE HANDLING ---
    switch (engine->output.state) {
        case STATE_OFF:
        case STATE_LOCKOUT:
        case STATE_METER_LOST:
            // Channel is de-energized; relay remains OFF
            engine->output.relay_commanded = false;
            engine->output.inrush_active = false;
            break;

        case STATE_INRUSH: {
            engine->output.relay_commanded = true;
            engine->output.inrush_active = true;

            // Inrush blanking suppresses overcurrent and overpower trips!
            // However, catastrophic voltage faults still trip immediately
            if (reading->voltage_v > (engine->limits.hard_max_voltage_v + 10.0f)) {
                engine->output.state = STATE_FAULT_RETRY;
                engine->output.relay_commanded = false;
                engine->output.inrush_active = false;
                engine->output.last_trip_reason = TRIP_OVER_VOLTAGE;
                engine->output.strike_count++;
                engine->retry_timer_ms = engine->limits.retry_delay_ms;
                break;
            }

            // Decrement inrush blanking timer
            if (engine->inrush_timer_ms <= dt_ms) {
                engine->inrush_timer_ms = 0;
                engine->output.inrush_active = false;
                engine->output.state = STATE_RUNNING;
            } else {
                engine->inrush_timer_ms -= dt_ms;
            }
            break;
        }

        case STATE_RUNNING: {
            engine->output.relay_commanded = true;
            engine->output.inrush_active = false;

            // Evaluate electrical fault conditions
            TripReason detected_reason = TRIP_NONE;

            if (reading->voltage_v > engine->limits.hard_max_voltage_v) {
                detected_reason = TRIP_OVER_VOLTAGE;
            } else if (reading->voltage_v < engine->limits.hard_min_voltage_v) {
                detected_reason = TRIP_UNDER_VOLTAGE;
            } else if (reading->current_a > eff_current_a) {
                detected_reason = TRIP_OVER_CURRENT;
            } else if (reading->active_power_w > eff_power_w) {
                detected_reason = TRIP_OVER_POWER;
            } else if (engine->limits.confirmed_min_pf > 0.0f &&
                       reading->power_factor < engine->limits.confirmed_min_pf &&
                       reading->current_a > 0.20f) {
                detected_reason = TRIP_LOW_POWER_FACTOR;
            } else if (reading->frequency_hz > engine->limits.hard_max_frequency_hz ||
                       reading->frequency_hz < engine->limits.hard_min_frequency_hz) {
                detected_reason = TRIP_FREQUENCY_OUT_OF_BOUNDS;
            }

            if (detected_reason != TRIP_NONE) {
                if (engine->pending_trip_reason == detected_reason) {
                    engine->debounce_timer_ms += dt_ms;
                } else {
                    engine->pending_trip_reason = detected_reason;
                    engine->debounce_timer_ms = dt_ms;
                }

                // If fault sustained beyond debounce threshold -> TRIP!
                if (engine->debounce_timer_ms >= engine->limits.trip_debounce_ms) {
                    engine->output.relay_commanded = false;
                    engine->output.last_trip_reason = detected_reason;
                    engine->output.strike_count++;
                    engine->debounce_timer_ms = 0;
                    engine->pending_trip_reason = TRIP_NONE;

                    if (engine->output.strike_count >= engine->limits.max_retry_strikes) {
                        engine->output.state = STATE_LOCKOUT;
                        engine->output.remaining_retry_ms = 0;
                    } else {
                        engine->output.state = STATE_FAULT_RETRY;
                        engine->retry_timer_ms = engine->limits.retry_delay_ms;
                        engine->output.remaining_retry_ms = engine->limits.retry_delay_ms;
                    }
                }
            } else {
                // Supply is normal; reset debounce filter
                engine->debounce_timer_ms = 0;
                engine->pending_trip_reason = TRIP_NONE;
            }
            break;
        }

        case STATE_FAULT_RETRY: {
            engine->output.relay_commanded = false;
            engine->output.inrush_active = false;

            // Cooldown requirement: Voltage must be stably within safe hysteresis band
            bool supply_stable = !engine->active_voltage_fault;

            if (supply_stable) {
                if (engine->retry_timer_ms <= dt_ms) {
                    engine->retry_timer_ms = 0;
                    engine->output.remaining_retry_ms = 0;
                    // Auto-retry switch-on! Enters inrush blanking
                    engine->output.state = STATE_INRUSH;
                    engine->output.relay_commanded = true;
                    engine->output.inrush_active = true;
                    engine->inrush_timer_ms = engine->limits.inrush_blanking_ms;
                } else {
                    engine->retry_timer_ms -= dt_ms;
                    engine->output.remaining_retry_ms = engine->retry_timer_ms;
                }
            } else {
                // If supply becomes unstable during cooldown, reset the 10-second timer!
                engine->retry_timer_ms = engine->limits.retry_delay_ms;
                engine->output.remaining_retry_ms = engine->limits.retry_delay_ms;
            }
            break;
        }
    }
}

const ProtectionOutput* protection_engine_get_output(const ProtectionEngine* engine) {
    return engine ? &engine->output : 0;
}

