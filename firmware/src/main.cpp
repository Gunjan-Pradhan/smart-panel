#ifdef ARDUINO
#include <Arduino.h>
#include <esp_task_wdt.h>
#include <esp_system.h>

#include "panel_config.h"
#include "protection_engine.h"
#include "zscore_detector.h"
#include "offline_buffer.h"
#include "relay_driver.h"
#include "pzem_reader.h"
#include "nvs_manager.h"
#include "led_buttons.h"
#include "mqtt_manager.h"

// System Components
static RelayChannel relay_ch1;
static RelayChannel relay_ch2;

static PZEMReader pzem_ch1;
static PZEMReader pzem_ch2;

static ProtectionEngine engine_ch1;
static ProtectionEngine engine_ch2;

static ZScoreBaseline zbaseline_ch1;
static ZScoreBaseline zbaseline_ch2;

static OfflineBuffer telemetry_buffer;
static NetworkSettings net_settings;
static LocalSchedule schedule_ch1;
static LocalSchedule schedule_ch2;

static uint32_t last_telemetry_pub_ms = 0;
static uint32_t last_heartbeat_pub_ms = 0;
static uint32_t last_protection_step_ms = 0;
static uint32_t boot_time_ms = 0;

// Command Callback from MQTT
static void handle_mqtt_command(
    const char* cmd_id,
    uint8_t channel,
    const char* action,
    uint32_t issued_at,
    uint32_t expires_at,
    const char* source
) {
    uint32_t now_s = (uint32_t)(millis() / 1000);
    bool turn_on = (strcmp(action, "ON") == 0);
    CommandReason reason = CMD_REASON_OK;
    CommandResult result = CMD_RESULT_DONE;
    ProtectionEngine* engine = (channel == 1) ? &engine_ch1 : ((channel == 2) ? &engine_ch2 : NULL);

    if (!engine) {
        mqtt_publish_ack(cmd_id, channel, CMD_RESULT_REJECTED, CMD_REASON_INVALID_CHANNEL, false, STATE_OFF, now_s);
        return;
    }

    if (strcmp(action, "ON") != 0 && strcmp(action, "OFF") != 0) {
        mqtt_publish_ack(cmd_id, channel, CMD_RESULT_REJECTED, CMD_REASON_INVALID_ACTION,
                         engine->output.relay_commanded, engine->output.state, now_s);
        return;
    }

    // Expiry check (allowing 2s skew)
    if (expires_at > 0 && (now_s > expires_at + 2)) {
        mqtt_publish_ack(cmd_id, channel, CMD_RESULT_REJECTED, CMD_REASON_CMD_EXPIRED,
                         engine->output.relay_commanded, engine->output.state, now_s);
        return;
    }

    result = protection_engine_handle_command(engine, turn_on, PRIORITY_USER, &reason);

    // Actuate physical relay to match state machine output
    if (channel == 1) {
        relay_set(&relay_ch1, engine->output.relay_commanded);
    } else {
        relay_set(&relay_ch2, engine->output.relay_commanded);
    }

    mqtt_publish_ack(cmd_id, channel, result, reason,
                     engine->output.relay_commanded, engine->output.state, now_s);
}

// Process Serial CLI Commands for Testing Without Mains
static void process_serial_cli(const String& cmd_line) {
    String cmd = cmd_line;
    cmd.trim();
    if (cmd.length() == 0) return;

    Serial.print(F("[CLI] > "));
    Serial.println(cmd);

    if (cmd.equalsIgnoreCase("STATUS")) {
        const ProtectionOutput* o1 = protection_engine_get_output(&engine_ch1);
        const ProtectionOutput* o2 = protection_engine_get_output(&engine_ch2);
        Serial.printf("CH1 (%s): Relay=%s State=%s Strikes=%u Reason=%s\n",
                      CH1_NAME, o1->relay_commanded ? "ON" : "OFF", channel_state_to_str(o1->state),
                      o1->strike_count, trip_reason_to_str(o1->last_trip_reason));
        Serial.printf("CH2 (%s): Relay=%s State=%s Strikes=%u Reason=%s\n",
                      CH2_NAME, o2->relay_commanded ? "ON" : "OFF", channel_state_to_str(o2->state),
                      o2->strike_count, trip_reason_to_str(o2->last_trip_reason));
        Serial.printf("Wi-Fi: %s | MQTT: %s | Buffer: %u/%u (Dropped: %u)\n",
                      WiFi.isConnected() ? "CONNECTED" : "DISCONNECTED",
                      mqtt_manager_is_connected() ? "CONNECTED" : "OFFLINE",
                      offline_buffer_count(&telemetry_buffer), OFFLINE_BUFFER_CAPACITY,
                      offline_buffer_dropped_total(&telemetry_buffer));
        return;
    }

    if (cmd.equalsIgnoreCase("RESET 1") || cmd.equalsIgnoreCase("RESET CH1")) {
        protection_engine_reset_lockout(&engine_ch1);
        relay_set(&relay_ch1, false);
        Serial.println(F("CH1 Lockout cleared. Channel reset to OFF."));
        return;
    }

    if (cmd.equalsIgnoreCase("RESET 2") || cmd.equalsIgnoreCase("RESET CH2")) {
        protection_engine_reset_lockout(&engine_ch2);
        relay_set(&relay_ch2, false);
        Serial.println(F("CH2 Lockout cleared. Channel reset to OFF."));
        return;
    }

    if (cmd.equalsIgnoreCase("ON 1") || cmd.equalsIgnoreCase("ON CH1")) {
        CommandReason reason;
        CommandResult res = protection_engine_handle_command(&engine_ch1, true, PRIORITY_USER, &reason);
        relay_set(&relay_ch1, engine_ch1.output.relay_commanded);
        Serial.printf("CH1 Command ON -> %s (%s)\n", cmd_result_to_str(res), cmd_reason_to_str(reason));
        return;
    }

    if (cmd.equalsIgnoreCase("OFF 1") || cmd.equalsIgnoreCase("OFF CH1")) {
        protection_engine_handle_command(&engine_ch1, false, PRIORITY_USER, NULL);
        relay_set(&relay_ch1, false);
        Serial.println(F("CH1 Command OFF -> DONE"));
        return;
    }

    if (cmd.equalsIgnoreCase("ON 2") || cmd.equalsIgnoreCase("ON CH2")) {
        CommandReason reason;
        CommandResult res = protection_engine_handle_command(&engine_ch2, true, PRIORITY_USER, &reason);
        relay_set(&relay_ch2, engine_ch2.output.relay_commanded);
        Serial.printf("CH2 Command ON -> %s (%s)\n", cmd_result_to_str(res), cmd_reason_to_str(reason));
        return;
    }

    if (cmd.equalsIgnoreCase("OFF 2") || cmd.equalsIgnoreCase("OFF CH2")) {
        protection_engine_handle_command(&engine_ch2, false, PRIORITY_USER, NULL);
        relay_set(&relay_ch2, false);
        Serial.println(F("CH2 Command OFF -> DONE"));
        return;
    }

    // Fault Injection Command: "inject ch1 v 285" or "inject ch1 i 12.5"
    if (cmd.startsWith("inject") || cmd.startsWith("INJECT")) {
        if (cmd.indexOf("clear") > 0 || cmd.indexOf("CLEAR") > 0) {
            pzem_clear_injection(&pzem_ch1);
            pzem_clear_injection(&pzem_ch2);
            Serial.println(F("[INJECTION] Cleared. Returned to live hardware meter polling."));
            return;
        }

        uint8_t target_ch = 1;
        if (cmd.indexOf("ch2") > 0 || cmd.indexOf("CH2") > 0) target_ch = 2;
        PZEMReader* pzem = (target_ch == 1) ? &pzem_ch1 : &pzem_ch2;

        float v = 230.0f, i = 0.8f, p = 120.0f, pf = 0.65f, f = 50.0f;
        if (pzem->injection_active) {
            v = pzem->injected_reading.voltage_v;
            i = pzem->injected_reading.current_a;
            p = pzem->injected_reading.active_power_w;
            pf = pzem->injected_reading.power_factor;
            f = pzem->injected_reading.frequency_hz;
        }

        int idx_v = cmd.indexOf(" v ");
        if (idx_v > 0) v = cmd.substring(idx_v + 3).toFloat();

        int idx_i = cmd.indexOf(" i ");
        if (idx_i > 0) i = cmd.substring(idx_i + 3).toFloat();

        int idx_p = cmd.indexOf(" p ");
        if (idx_p > 0) p = cmd.substring(idx_p + 3).toFloat();

        int idx_pf = cmd.indexOf(" pf ");
        if (idx_pf > 0) pf = cmd.substring(idx_pf + 4).toFloat();

        pzem_inject_fault(pzem, v, i, p, pf, f, true);
        Serial.printf("[INJECTION ACTIVE] CH%u -> V=%.1f V | I=%.3f A | P=%.1f W | PF=%.2f | F=%.1f Hz\n",
                      target_ch, v, i, p, pf, f);
        return;
    }

    Serial.println(F("Commands: STATUS | ON <1|2> | OFF <1|2> | RESET <1|2> | INJECT CH<1|2> V|I|P|PF <val> | INJECT CLEAR"));
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println(F("\n========================================================"));
    Serial.printf("  SMART LOAD PROTECTION PANEL FIRMWARE v%s\n", FIRMWARE_VERSION);
    Serial.println(F("  Deterministic Edge Protection & Load Management"));
    Serial.println(F("========================================================"));

    // 1. LAYER 1: SAFE BOOT
    // Pre-loads idle logic levels into output register before configuring pins as OUTPUT
    relay_init(&relay_ch1, CH1_RELAY_PIN, CH1_RELAY_ACTIVE_LOW);
    relay_init(&relay_ch2, CH2_RELAY_PIN, CH2_RELAY_ACTIVE_LOW);
    Serial.printf("[SAFE BOOT] Relays Initialized OFF: CH1 (GPIO%u Active-LOW), CH2 (GPIO%u Active-HIGH)\n",
                  CH1_RELAY_PIN, CH2_RELAY_PIN);

    // Hardware Watchdog setup (10 s timeout)
    esp_task_wdt_init(WATCHDOG_TIMEOUT_S, true);
    esp_task_wdt_add(NULL); // Add current loop task
    Serial.printf("[WATCHDOG] Hardware task watchdog enabled (%u s)\n", WATCHDOG_TIMEOUT_S);

    // 2. LAYER 4: NVS SETTINGS LOAD
    nvs_manager_init();
    ChannelLimits lim1, lim2;
    protection_engine_init(&engine_ch1, NULL);
    protection_engine_init(&engine_ch2, NULL);

    engine_ch1.limits.inrush_blanking_ms = CH1_INRUSH_BLANKING_MS;
    engine_ch2.limits.inrush_blanking_ms = CH2_INRUSH_BLANKING_MS;

    if (nvs_load_limits(1, &lim1)) protection_engine_update_limits(&engine_ch1, &lim1);
    if (nvs_load_limits(2, &lim2)) protection_engine_update_limits(&engine_ch2, &lim2);

    if (!nvs_load_network_settings(&net_settings)) {
        strncpy(net_settings.wifi_ssid, DEFAULT_WIFI_SSID, sizeof(net_settings.wifi_ssid));
        strncpy(net_settings.wifi_pass, DEFAULT_WIFI_PASS, sizeof(net_settings.wifi_pass));
        strncpy(net_settings.mqtt_host, DEFAULT_MQTT_HOST, sizeof(net_settings.mqtt_host));
        net_settings.mqtt_port = DEFAULT_MQTT_PORT;
        strncpy(net_settings.device_id, DEFAULT_DEVICE_ID, sizeof(net_settings.device_id));
    }

    nvs_load_schedule(1, &schedule_ch1);
    nvs_load_schedule(2, &schedule_ch2);

    // 3. LAYER 2: METER READING INITIALIZATION
    pzem_reader_init(&pzem_ch1, 1, CH1_UART_NUM, CH1_RX_PIN, CH1_TX_PIN, 0x01);
    pzem_reader_init(&pzem_ch2, 2, CH2_UART_NUM, CH2_RX_PIN, CH2_TX_PIN, 0x02);
    Serial.println(F("[METER] Dual PZEM-004T Serial buses initialized (UART1 & UART2)"));

    // 4. LAYER 5: UI PERIPHERALS (LEDs & BUTTONS)
    ui_peripherals_init();

    // 5. LAYER 7: OFFLINE BUFFER INITIALIZATION
    offline_buffer_init(&telemetry_buffer);

    // 6. LAYER 10: EDGE Z-SCORE DETECTOR
    zscore_init(&zbaseline_ch1);
    zscore_init(&zbaseline_ch2);

    // 7. LAYER 6 & 8: WI-FI & MQTT
    mqtt_manager_init(net_settings.device_id, handle_mqtt_command);
    mqtt_manager_set_credentials(
        net_settings.wifi_ssid,
        net_settings.wifi_pass,
        net_settings.mqtt_host,
        net_settings.mqtt_port
    );

    boot_time_ms = millis();
    last_protection_step_ms = boot_time_ms;
    Serial.println(F("[SYSTEM] Initialization Complete. Entering Real-Time Protection Loop.\n"));
}

void loop() {
    // Reset hardware watchdog
    esp_task_wdt_reset();

    uint32_t now_ms = millis();
    uint32_t dt_ms = now_ms - last_protection_step_ms;
    if (dt_ms >= 50) { // Execute protection step every 50 ms
        last_protection_step_ms = now_ms;

        // Poll meter readings
        ElectricalReading r1, r2;
        pzem_poll_reading(&pzem_ch1, &r1);
        pzem_poll_reading(&pzem_ch2, &r2);

        // Execute deterministic protection state machines
        protection_engine_step(&engine_ch1, &r1, dt_ms);
        protection_engine_step(&engine_ch2, &r2, dt_ms);

        // Hardware actuation: sync physical relays to state machine decisions
        relay_set(&relay_ch1, engine_ch1.output.relay_commanded);
        relay_set(&relay_ch2, engine_ch2.output.relay_commanded);

        // Update LEDs and check buttons
        ui_update_leds(WiFi.isConnected(), engine_ch1.output.state, engine_ch2.output.state, now_ms);
        ButtonEvents btn_ev = ui_poll_buttons(now_ms);

        if (btn_ev.btn_reset_pressed) {
            Serial.println(F("[BUTTON] Reset pressed: clearing lockouts and forcing safe state."));
            protection_engine_reset_lockout(&engine_ch1);
            protection_engine_reset_lockout(&engine_ch2);
            relay_set(&relay_ch1, false);
            relay_set(&relay_ch2, false);
        }

        if (btn_ev.btn_learn_pressed) {
            Serial.println(F("[BUTTON] Learn pressed: emitting local load learning trigger event."));
            mqtt_publish_event("LEARN_REQUESTED", "info", 1, "Manual learn button pressed", (uint32_t)(now_ms / 1000));
        }

        // Layer 10: Edge Z-score anomaly evaluation (advisory warning only!)
        ZScoreResult zres1 = zscore_evaluate(&zbaseline_ch1, r1.voltage_v, r1.current_a, r1.active_power_w, r1.power_factor);
        if (zres1.is_anomaly && engine_ch1.output.state == STATE_RUNNING) {
            mqtt_publish_event("EDGE_ZSCORE_ANOMALY", "warning", 1, "Edge Z-Score anomaly threshold exceeded", (uint32_t)(now_ms / 1000));
        }

        // Periodic Telemetry Publishing (1 Hz)
        if (now_ms - last_telemetry_pub_ms >= TELEMETRY_INTERVAL_MS) {
            last_telemetry_pub_ms = now_ms;
            bool online = mqtt_manager_is_connected();

            if (online) {
                mqtt_publish_telemetry(1, &r1, engine_ch1.output.relay_commanded, engine_ch1.output.state, false, true);
                mqtt_publish_telemetry(2, &r2, engine_ch2.output.relay_commanded, engine_ch2.output.state, false, true);
                mqtt_drain_offline_buffer(&telemetry_buffer);
            } else {
                // Buffer readings in PSRAM / ring buffer while offline
                BufferedTelemetryItem item1 = { 1, (uint32_t)(now_ms / 1000), r1.voltage_v, r1.current_a,
                                               r1.active_power_w, r1.energy_kwh, r1.power_factor, r1.frequency_hz,
                                               engine_ch1.output.relay_commanded, engine_ch1.output.state, false };
                BufferedTelemetryItem item2 = { 2, (uint32_t)(now_ms / 1000), r2.voltage_v, r2.current_a,
                                               r2.active_power_w, r2.energy_kwh, r2.power_factor, r2.frequency_hz,
                                               engine_ch2.output.relay_commanded, engine_ch2.output.state, false };
                offline_buffer_push(&telemetry_buffer, &item1);
                offline_buffer_push(&telemetry_buffer, &item2);
            }
        }

        // Periodic Heartbeat (60 s)
        if (now_ms - last_heartbeat_pub_ms >= HEARTBEAT_INTERVAL_MS) {
            last_heartbeat_pub_ms = now_ms;
            uint32_t uptime_s = (uint32_t)((now_ms - boot_time_ms) / 1000);
            int8_t rssi = WiFi.isConnected() ? (int8_t)WiFi.RSSI() : 0;
            mqtt_publish_status(
                mqtt_manager_is_connected(),
                uptime_s,
                rssi,
                esp_get_free_heap_size(),
                offline_buffer_count(&telemetry_buffer),
                offline_buffer_dropped_total(&telemetry_buffer),
                &engine_ch1.output,
                &engine_ch2.output,
                "periodic"
            );
        }
    }

    // Communication loop
    mqtt_manager_loop(now_ms);

    // Process incoming Serial CLI characters
    if (Serial.available()) {
        String input = Serial.readStringUntil('\n');
        process_serial_cli(input);
    }
}
#endif

