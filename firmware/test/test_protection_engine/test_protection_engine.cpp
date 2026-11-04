#include <unity.h>
#include <string.h>
#include "protection_engine.h"

static ProtectionEngine engine;
static ChannelLimits test_limits;

static ElectricalReading make_reading(float v, float i, float p, float pf, float f, bool valid) {
    ElectricalReading r;
    memset(&r, 0, sizeof(r));
    r.voltage_v = v;
    r.current_a = i;
    r.active_power_w = p;
    r.power_factor = pf;
    r.frequency_hz = f;
    r.valid = valid;
    r.timestamp_s = 1000;
    return r;
}

void setUp(void) {
    memset(&test_limits, 0, sizeof(test_limits));
    test_limits.hard_max_voltage_v = 275.0f;
    test_limits.hard_min_voltage_v = 175.0f;
    test_limits.hard_max_current_a = 10.0f;
    test_limits.hard_max_power_w = 2300.0f;
    test_limits.hard_min_frequency_hz = 45.0f;
    test_limits.hard_max_frequency_hz = 65.0f;

    test_limits.confirmed_current_a = 1.0f;  // Confirmed 1.0 A limit (e.g. for motor)
    test_limits.confirmed_power_w = 200.0f;  // Confirmed 200 W limit
    test_limits.confirmed_min_pf = 0.50f;

    test_limits.inrush_blanking_ms = 2000;   // 2 second inrush
    test_limits.trip_debounce_ms = 150;      // 150 ms debounce
    test_limits.retry_delay_ms = 10000;      // 10 second retry
    test_limits.max_retry_strikes = 3;       // 3 strikes to lockout
    test_limits.meter_fail_limit = 5;

    test_limits.voltage_hysteresis_v = 5.0f;
    test_limits.current_hysteresis_a = 0.10f;

    protection_engine_init(&engine, &test_limits);
}

void tearDown(void) {
}

// 1. Initial State: Must be safe boot OFF
void test_initial_state_safe_boot_off(void) {
    const ProtectionOutput* out = protection_engine_get_output(&engine);
    TEST_ASSERT_EQUAL_INT(STATE_OFF, out->state);
    TEST_ASSERT_FALSE(out->relay_commanded);
    TEST_ASSERT_EQUAL_INT(0, out->strike_count);
    TEST_ASSERT_EQUAL_INT(TRIP_NONE, out->last_trip_reason);
}

// 2. Command ON enters INRUSH state
void test_command_on_enters_inrush(void) {
    CommandReason reason;
    CommandResult res = protection_engine_handle_command(&engine, true, PRIORITY_USER, &reason);

    TEST_ASSERT_EQUAL_INT(CMD_RESULT_DONE, res);
    TEST_ASSERT_EQUAL_INT(CMD_REASON_OK, reason);

    const ProtectionOutput* out = protection_engine_get_output(&engine);
    TEST_ASSERT_EQUAL_INT(STATE_INRUSH, out->state);
    TEST_ASSERT_TRUE(out->relay_commanded);
    TEST_ASSERT_TRUE(out->inrush_active);
}

// 3. Inrush Blanking: High startup current (3x rated) is suppressed during inrush window
void test_inrush_blanking_suppresses_overcurrent_surge(void) {
    protection_engine_handle_command(&engine, true, PRIORITY_USER, NULL);

    // Motor surges to 4.5 A (limit is 1.0 A!)
    ElectricalReading surge = make_reading(230.0f, 4.5f, 600.0f, 0.60f, 50.0f, true);

    // Step 500 ms through inrush (total inrush is 2000 ms)
    for (int i = 0; i < 5; i++) {
        protection_engine_step(&engine, &surge, 100);
    }

    const ProtectionOutput* out = protection_engine_get_output(&engine);
    // Must STILL be in INRUSH and relay MUST NOT trip!
    TEST_ASSERT_EQUAL_INT(STATE_INRUSH, out->state);
    TEST_ASSERT_TRUE(out->relay_commanded);
    TEST_ASSERT_EQUAL_INT(0, out->strike_count);
}

// 4. Inrush Expiry: Normalizes to RUNNING after window elapses
void test_inrush_transitions_to_running(void) {
    protection_engine_handle_command(&engine, true, PRIORITY_USER, NULL);

    ElectricalReading normal = make_reading(230.0f, 0.8f, 120.0f, 0.65f, 50.0f, true);

    // Step past 2000 ms (21 x 100ms = 2100 ms)
    for (int i = 0; i < 21; i++) {
        protection_engine_step(&engine, &normal, 100);
    }

    const ProtectionOutput* out = protection_engine_get_output(&engine);
    TEST_ASSERT_EQUAL_INT(STATE_RUNNING, out->state);
    TEST_ASSERT_TRUE(out->relay_commanded);
    TEST_ASSERT_FALSE(out->inrush_active);
}

// 5. Debounce Filtering: Spikes shorter than debounce threshold (150ms) do not trip
void test_debounce_ignores_brief_spike(void) {
    protection_engine_handle_command(&engine, true, PRIORITY_USER, NULL);

    ElectricalReading normal = make_reading(230.0f, 0.8f, 120.0f, 0.65f, 50.0f, true);
    for (int i = 0; i < 21; i++) {
        protection_engine_step(&engine, &normal, 100);
    }

    // Single 50ms spike (debounce is 150ms)
    ElectricalReading spike = make_reading(230.0f, 2.5f, 400.0f, 0.65f, 50.0f, true);
    protection_engine_step(&engine, &spike, 50);

    // Immediately back to normal
    protection_engine_step(&engine, &normal, 100);

    const ProtectionOutput* out = protection_engine_get_output(&engine);
    // Did NOT trip because spike was shorter than 150ms
    TEST_ASSERT_EQUAL_INT(STATE_RUNNING, out->state);
    TEST_ASSERT_TRUE(out->relay_commanded);
    TEST_ASSERT_EQUAL_INT(0, out->strike_count);
}

// 6. Sustained Overcurrent: Trips channel and enters FAULT_RETRY after debounce
void test_sustained_overcurrent_trips_to_fault_retry(void) {
    protection_engine_handle_command(&engine, true, PRIORITY_USER, NULL);

    ElectricalReading normal = make_reading(230.0f, 0.8f, 120.0f, 0.65f, 50.0f, true);
    for (int i = 0; i < 21; i++) {
        protection_engine_step(&engine, &normal, 100);
    }

    // Sustained overcurrent (2.0 A for 200 ms > 150 ms debounce)
    ElectricalReading overload = make_reading(230.0f, 2.0f, 350.0f, 0.65f, 50.0f, true);
    protection_engine_step(&engine, &overload, 100);
    protection_engine_step(&engine, &overload, 100);

    const ProtectionOutput* out = protection_engine_get_output(&engine);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT_RETRY, out->state);
    TEST_ASSERT_FALSE(out->relay_commanded);
    TEST_ASSERT_EQUAL_INT(1, out->strike_count);
    TEST_ASSERT_EQUAL_INT(TRIP_OVER_CURRENT, out->last_trip_reason);
    TEST_ASSERT_EQUAL_UINT32(10000, out->remaining_retry_ms);
}

// 7. Auto-Retry: Re-arms after 10 s of stable supply
void test_auto_retry_recovers_after_delay(void) {
    test_sustained_overcurrent_trips_to_fault_retry();

    ElectricalReading safe_supply = make_reading(230.0f, 0.0f, 0.0f, 1.0f, 50.0f, true);

    // Step 10 seconds (101 steps of 100ms = 10100 ms)
    for (int i = 0; i < 101; i++) {
        protection_engine_step(&engine, &safe_supply, 100);
    }

    const ProtectionOutput* out = protection_engine_get_output(&engine);
    // After 10s cooldown, it automatically re-arms into INRUSH!
    TEST_ASSERT_EQUAL_INT(STATE_INRUSH, out->state);
    TEST_ASSERT_TRUE(out->relay_commanded);
    TEST_ASSERT_EQUAL_INT(1, out->strike_count); // Strike preserved
}

// 8. 3-Strike Lockout: 3 consecutive faults lock the channel out
void test_three_strikes_cause_permanent_lockout(void) {
    ElectricalReading overload = make_reading(230.0f, 2.5f, 400.0f, 0.65f, 50.0f, true);
    ElectricalReading safe_cooldown = make_reading(230.0f, 0.0f, 0.0f, 1.0f, 50.0f, true);

    // Strike 1
    protection_engine_handle_command(&engine, true, PRIORITY_USER, NULL);
    for (int i = 0; i < 21; i++) protection_engine_step(&engine, &safe_cooldown, 100);
    protection_engine_step(&engine, &overload, 100);
    protection_engine_step(&engine, &overload, 100);
    TEST_ASSERT_EQUAL_INT(1, protection_engine_get_output(&engine)->strike_count);

    // Cooldown 10s -> Strike 2
    for (int i = 0; i < 101; i++) protection_engine_step(&engine, &safe_cooldown, 100);
    for (int i = 0; i < 21; i++) protection_engine_step(&engine, &safe_cooldown, 100);
    protection_engine_step(&engine, &overload, 100);
    protection_engine_step(&engine, &overload, 100);
    TEST_ASSERT_EQUAL_INT(2, protection_engine_get_output(&engine)->strike_count);

    // Cooldown 10s -> Strike 3 (Final!)
    for (int i = 0; i < 101; i++) protection_engine_step(&engine, &safe_cooldown, 100);
    for (int i = 0; i < 21; i++) protection_engine_step(&engine, &safe_cooldown, 100);
    protection_engine_step(&engine, &overload, 100);
    protection_engine_step(&engine, &overload, 100);

    const ProtectionOutput* out = protection_engine_get_output(&engine);
    TEST_ASSERT_EQUAL_INT(STATE_LOCKOUT, out->state);
    TEST_ASSERT_FALSE(out->relay_commanded);
    TEST_ASSERT_EQUAL_INT(3, out->strike_count);
}

// 9. User Command ON is REFUSED during Lockout
void test_user_command_refused_in_lockout(void) {
    test_three_strikes_cause_permanent_lockout();

    CommandReason reason;
    CommandResult res = protection_engine_handle_command(&engine, true, PRIORITY_USER, &reason);

    TEST_ASSERT_EQUAL_INT(CMD_RESULT_REJECTED, res);
    TEST_ASSERT_EQUAL_INT(CMD_REASON_SAFETY_LOCKOUT, reason);

    // Relay remains OFF
    const ProtectionOutput* out = protection_engine_get_output(&engine);
    TEST_ASSERT_EQUAL_INT(STATE_LOCKOUT, out->state);
    TEST_ASSERT_FALSE(out->relay_commanded);
}

// 10. Manual Reset clears Lockout
void test_manual_reset_clears_lockout(void) {
    test_three_strikes_cause_permanent_lockout();

    protection_engine_reset_lockout(&engine);

    const ProtectionOutput* out = protection_engine_get_output(&engine);
    TEST_ASSERT_EQUAL_INT(STATE_OFF, out->state);
    TEST_ASSERT_FALSE(out->relay_commanded);
    TEST_ASSERT_EQUAL_INT(0, out->strike_count);

    // Now turning ON is allowed again
    CommandReason reason;
    CommandResult res = protection_engine_handle_command(&engine, true, PRIORITY_USER, &reason);
    TEST_ASSERT_EQUAL_INT(CMD_RESULT_DONE, res);
}

// 11. Meter Lost: 5 consecutive invalid readings forces METER_LOST and trips relay
void test_meter_lost_handling(void) {
    protection_engine_handle_command(&engine, true, PRIORITY_USER, NULL);

    ElectricalReading bad_reading = make_reading(0.0f, 0.0f, 0.0f, 0.0f, 0.0f, false);

    // 5 consecutive dropped packets
    for (int i = 0; i < 5; i++) {
        protection_engine_step(&engine, &bad_reading, 100);
    }

    const ProtectionOutput* out = protection_engine_get_output(&engine);
    TEST_ASSERT_EQUAL_INT(STATE_METER_LOST, out->state);
    TEST_ASSERT_FALSE(out->relay_commanded);
    TEST_ASSERT_EQUAL_INT(TRIP_METER_LOST, out->last_trip_reason);

    // New ON command must be rejected
    CommandReason reason;
    CommandResult res = protection_engine_handle_command(&engine, true, PRIORITY_USER, &reason);
    TEST_ASSERT_EQUAL_INT(CMD_RESULT_REJECTED, res);
    TEST_ASSERT_EQUAL_INT(CMD_REASON_METER_FAULT, reason);
}

// 12. Clamping: Effective limit is clamped to hard cap
void test_effective_limits_clamped_to_hard_caps(void) {
    ChannelLimits excessive_limits = test_limits;
    excessive_limits.confirmed_current_a = 50.0f; // Above 10.0 A hard cap!
    excessive_limits.confirmed_power_w = 9000.0f; // Above 2300 W hard cap!

    protection_engine_init(&engine, &excessive_limits);

    float eff_i = 0.0f;
    float eff_p = 0.0f;
    protection_engine_get_effective_limits(&engine, &eff_i, &eff_p);

    TEST_ASSERT_EQUAL_FLOAT(10.0f, eff_i);   // Clamped to hard max current
    TEST_ASSERT_EQUAL_FLOAT(2300.0f, eff_p); // Clamped to hard max power
}

int main(int argc, char **argv) {
    UNITY_BEGIN();
    RUN_TEST(test_initial_state_safe_boot_off);
    RUN_TEST(test_command_on_enters_inrush);
    RUN_TEST(test_inrush_blanking_suppresses_overcurrent_surge);
    RUN_TEST(test_inrush_transitions_to_running);
    RUN_TEST(test_debounce_ignores_brief_spike);
    RUN_TEST(test_sustained_overcurrent_trips_to_fault_retry);
    RUN_TEST(test_auto_retry_recovers_after_delay);
    RUN_TEST(test_three_strikes_cause_permanent_lockout);
    RUN_TEST(test_user_command_refused_in_lockout);
    RUN_TEST(test_manual_reset_clears_lockout);
    RUN_TEST(test_meter_lost_handling);
    RUN_TEST(test_effective_limits_clamped_to_hard_caps);
    return UNITY_END();
}
