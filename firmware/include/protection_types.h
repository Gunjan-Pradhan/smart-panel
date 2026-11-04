#ifndef PROTECTION_TYPES_H
#define PROTECTION_TYPES_H

#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

// Channel Operating State Machine per docs/mqtt_contract.md §5.3
typedef enum {
    STATE_OFF = 0,        // Relay commanded open; load disconnected
    STATE_INRUSH = 1,     // Startup transient window; overcurrent trip blanked
    STATE_RUNNING = 2,    // Steady monitoring; all protection limits active
    STATE_FAULT_RETRY = 3,// Tripped on fault; waiting for stable cooldown
    STATE_LOCKOUT = 4,    // 3 strikes reached; manual/authorized reset required
    STATE_METER_LOST = 5  // N consecutive meter read failures; forced OFF
} ChannelState;

// Trip Reason Codes per docs/mqtt_contract.md §7.1
typedef enum {
    TRIP_NONE = 0,
    TRIP_OVER_VOLTAGE,
    TRIP_UNDER_VOLTAGE,
    TRIP_OVER_CURRENT,
    TRIP_OVER_POWER,
    TRIP_LOW_POWER_FACTOR,
    TRIP_FREQUENCY_OUT_OF_BOUNDS,
    TRIP_METER_LOST,
    TRIP_MANUAL_OFF
} TripReason;

// Command Result Codes per docs/mqtt_contract.md §9.1
typedef enum {
    CMD_RESULT_DONE = 0,
    CMD_RESULT_REJECTED,
    CMD_RESULT_FAILED
} CommandResult;

typedef enum {
    CMD_REASON_OK = 0,
    CMD_REASON_SAFETY_LOCKOUT,
    CMD_REASON_ACTIVE_FAULT,
    CMD_REASON_INVALID_CHANNEL,
    CMD_REASON_INVALID_ACTION,
    CMD_REASON_INVALID_PAYLOAD,
    CMD_REASON_CMD_EXPIRED,
    CMD_REASON_METER_FAULT,
    CMD_REASON_INTERNAL_ERROR
} CommandReason;

// Control Authority Priority (Lowest numeric value = Highest authority)
typedef enum {
    PRIORITY_SAFETY = 1,       // Local deterministic protection (highest)
    PRIORITY_SCHEDULE = 2,     // Operator-configured local schedules
    PRIORITY_USER = 3,         // Manual authorized operator command
    PRIORITY_OPTIMIZATION = 4, // Accepted automated energy policies
    PRIORITY_ADVISORY = 5      // AI advisory signals (cannot switch relays)
} ControlPriority;

// Raw or filtered electrical measurement from PZEM-004T
typedef struct {
    float voltage_v;
    float current_a;
    float active_power_w;
    float power_factor;
    float frequency_hz;
    float energy_kwh;
    bool valid;
    uint32_t timestamp_s;
} ElectricalReading;

// Protection Thresholds & Timing Parameters
typedef struct {
    // Hard Caps (Hardware protection boundaries - never changed by software)
    float hard_max_voltage_v;     // Default: 275.0 V
    float hard_min_voltage_v;     // Default: 175.0 V
    float hard_max_current_a;     // Default: 16.0 A
    float hard_max_power_w;       // Default: 3600.0 W
    float hard_min_frequency_hz;  // Default: 45.0 Hz
    float hard_max_frequency_hz;  // Default: 65.0 Hz

    // Confirmed User Limits (Derived from appliance rating, NULL/0 if unconfirmed)
    float confirmed_current_a;    // 0 = unconfirmed
    float confirmed_power_w;      // 0 = unconfirmed
    float confirmed_min_pf;       // 0 = unconfirmed (e.g. 0.50)

    // Timing and Debounce Parameters
    uint32_t inrush_blanking_ms;  // Motor: 2000 ms; Bulbs: 50 ms
    uint32_t trip_debounce_ms;    // Sustained fault duration before trip (e.g. 150 ms)
    uint32_t retry_delay_ms;      // Cooldown wait before retry (default: 10000 ms = 10 s)
    uint8_t  max_retry_strikes;   // Strikes before lockout (default: 3)
    uint8_t  meter_fail_limit;    // Consecutive read failures before METER_LOST (default: 5)
    
    // Hysteresis Margins for safe recovery
    float voltage_hysteresis_v;   // e.g. 5.0 V
    float current_hysteresis_a;   // e.g. 0.10 A
} ChannelLimits;

// Current state output of the protection engine
typedef struct {
    ChannelState state;
    bool relay_commanded;         // true = ON/Closed, false = OFF/Open
    TripReason last_trip_reason;
    uint8_t strike_count;
    bool inrush_active;
    uint32_t remaining_retry_ms;
    uint8_t consecutive_meter_fails;
} ProtectionOutput;

// Helper to convert state to string representation per contract
static inline const char* channel_state_to_str(ChannelState s) {
    switch (s) {
        case STATE_OFF: return "OFF";
        case STATE_INRUSH: return "STARTING";
        case STATE_RUNNING: return "RUNNING";
        case STATE_FAULT_RETRY: return "RETRY_WAIT";
        case STATE_LOCKOUT: return "LOCKED_OUT";
        case STATE_METER_LOST: return "METER_FAULT";
        default: return "OFF";
    }
}

// Helper to convert trip reason to string
static inline const char* trip_reason_to_str(TripReason r) {
    switch (r) {
        case TRIP_NONE: return "NONE";
        case TRIP_OVER_VOLTAGE: return "OVER_VOLTAGE";
        case TRIP_UNDER_VOLTAGE: return "UNDER_VOLTAGE";
        case TRIP_OVER_CURRENT: return "OVER_CURRENT";
        case TRIP_OVER_POWER: return "OVER_POWER";
        case TRIP_LOW_POWER_FACTOR: return "LOW_POWER_FACTOR";
        case TRIP_FREQUENCY_OUT_OF_BOUNDS: return "FREQUENCY_OUT_OF_BOUNDS";
        case TRIP_METER_LOST: return "METER_LOST";
        case TRIP_MANUAL_OFF: return "MANUAL_OFF";
        default: return "UNKNOWN";
    }
}

// Helper to convert command result and reason to string
static inline const char* cmd_result_to_str(CommandResult r) {
    switch (r) {
        case CMD_RESULT_DONE: return "DONE";
        case CMD_RESULT_REJECTED: return "REJECTED";
        case CMD_RESULT_FAILED: return "FAILED";
        default: return "FAILED";
    }
}

static inline const char* cmd_reason_to_str(CommandReason r) {
    switch (r) {
        case CMD_REASON_OK: return "OK";
        case CMD_REASON_SAFETY_LOCKOUT: return "SAFETY_LOCKOUT";
        case CMD_REASON_ACTIVE_FAULT: return "ACTIVE_FAULT";
        case CMD_REASON_INVALID_CHANNEL: return "INVALID_CHANNEL";
        case CMD_REASON_INVALID_ACTION: return "INVALID_ACTION";
        case CMD_REASON_INVALID_PAYLOAD: return "INVALID_PAYLOAD";
        case CMD_REASON_CMD_EXPIRED: return "CMD_EXPIRED";
        case CMD_REASON_METER_FAULT: return "METER_FAULT";
        case CMD_REASON_INTERNAL_ERROR: return "INTERNAL_ERROR";
        default: return "INTERNAL_ERROR";
    }
}

#ifdef __cplusplus
}
#endif

#endif // PROTECTION_TYPES_H

