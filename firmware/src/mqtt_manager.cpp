#include "mqtt_manager.h"
#include <stdio.h>
#include <string.h>

#ifdef ARDUINO
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

static WiFiClient wifi_client;
static PubSubClient mqtt_client(wifi_client);
static CommandHandlerCallback registered_cmd_cb = NULL;
static char current_device_id[32] = "PANEL-0001";
static char topic_cmd[64];
static char topic_ack[64];
static char topic_event[64];
static char topic_status[64];
static char topic_telemetry_prefix[64];

static uint32_t last_wifi_reconnect_attempt = 0;
static uint32_t last_mqtt_reconnect_attempt = 0;
static char wifi_ssid[32] = "SmartPanel_AP";
static char wifi_pass[64] = "protection2026";
static char mqtt_host[64] = "127.0.0.1";
static uint16_t mqtt_port = 1883;

static void mqtt_callback(char* topic, byte* payload, unsigned int length) {
    if (!registered_cmd_cb || length == 0) return;

    // Allocate buffer for JSON parse
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, payload, length);
    if (err) return;

    const char* cmd_id = doc["cmd_id"] | "";
    uint8_t ch = doc["ch"] | 0;
    const char* action = doc["action"] | "";
    uint32_t issued_at = doc["issued_at"] | 0;
    uint32_t expires_at = doc["expires_at"] | 0;
    const char* source = doc["source"] | "user";

    registered_cmd_cb(cmd_id, ch, action, issued_at, expires_at, source);
}

void mqtt_manager_init(const char* device_id, CommandHandlerCallback cmd_cb) {
    if (device_id) strncpy(current_device_id, device_id, sizeof(current_device_id) - 1);
    registered_cmd_cb = cmd_cb;

    snprintf(topic_cmd, sizeof(topic_cmd), "panel/%s/cmd", current_device_id);
    snprintf(topic_ack, sizeof(topic_ack), "panel/%s/ack", current_device_id);
    snprintf(topic_event, sizeof(topic_event), "panel/%s/event", current_device_id);
    snprintf(topic_status, sizeof(topic_status), "panel/%s/status", current_device_id);
    snprintf(topic_telemetry_prefix, sizeof(topic_telemetry_prefix), "panel/%s/telemetry", current_device_id);

    mqtt_client.setCallback(mqtt_callback);
    mqtt_client.setBufferSize(1024);
}

void mqtt_manager_set_credentials(const char* ssid, const char* pass, const char* host, uint16_t port) {
    if (ssid) strncpy(wifi_ssid, ssid, sizeof(wifi_ssid) - 1);
    if (pass) strncpy(wifi_pass, pass, sizeof(wifi_pass) - 1);
    if (host) strncpy(mqtt_host, host, sizeof(mqtt_host) - 1);
    mqtt_port = port;

    mqtt_client.setServer(mqtt_host, mqtt_port);
}

static void reconnect_wifi(uint32_t now_ms) {
    if (WiFi.status() == WL_CONNECTED) return;

    if (now_ms - last_wifi_reconnect_attempt > 10000) {
        last_wifi_reconnect_attempt = now_ms;
        WiFi.begin(wifi_ssid, wifi_pass);
    }
}

static void reconnect_mqtt(uint32_t now_ms) {
    if (mqtt_client.connected()) return;
    if (WiFi.status() != WL_CONNECTED) return;

    if (now_ms - last_mqtt_reconnect_attempt > 5000) {
        last_mqtt_reconnect_attempt = now_ms;

        // Last Will and Testament Payload
        char lwt_payload[128];
        snprintf(lwt_payload, sizeof(lwt_payload),
                 "{\"schema\":1,\"ts\":0,\"online\":false,\"device_id\":\"%s\",\"reason\":\"lwt\"}",
                 current_device_id);

        if (mqtt_client.connect(current_device_id, topic_status, 1, true, lwt_payload)) {
            mqtt_client.subscribe(topic_cmd, 1);
        }
    }
}

bool mqtt_manager_loop(uint32_t now_ms) {
    reconnect_wifi(now_ms);
    reconnect_mqtt(now_ms);

    if (mqtt_client.connected()) {
        mqtt_client.loop();
        return true;
    }
    return false;
}

bool mqtt_manager_is_connected(void) {
    return mqtt_client.connected();
}

void mqtt_publish_telemetry(
    uint8_t channel,
    const ElectricalReading* reading,
    bool relay_state,
    ChannelState state,
    bool buffered,
    bool clock_synced
) {
    if (!reading || !mqtt_client.connected()) return;

    char topic[64];
    snprintf(topic, sizeof(topic), "%s/%u", topic_telemetry_prefix, channel);

    JsonDocument doc;
    doc["schema"] = 1;
    doc["ts"] = reading->timestamp_s;
    doc["ch"] = channel;
    doc["v"] = serialized(String(reading->voltage_v, 2));
    doc["i"] = serialized(String(reading->current_a, 3));
    doc["p"] = serialized(String(reading->active_power_w, 2));
    doc["e_kwh"] = serialized(String(reading->energy_kwh, 3));
    doc["pf"] = serialized(String(reading->power_factor, 3));
    doc["f"] = serialized(String(reading->frequency_hz, 2));
    doc["relay"] = relay_state;
    doc["state"] = channel_state_to_str(state);
    doc["buffered"] = buffered;
    doc["clock_synced"] = clock_synced;

    char payload[384];
    size_t len = serializeJson(doc, payload, sizeof(payload));
    mqtt_client.publish(topic, (const uint8_t*)payload, len, false);
}

void mqtt_publish_ack(
    const char* cmd_id,
    uint8_t channel,
    CommandResult result,
    CommandReason reason,
    bool relay_state,
    ChannelState state,
    uint32_t timestamp_s
) {
    if (!mqtt_client.connected()) return;

    JsonDocument doc;
    doc["schema"] = 1;
    doc["cmd_id"] = cmd_id;
    doc["ch"] = channel;
    doc["result"] = cmd_result_to_str(result);
    doc["reason"] = cmd_reason_to_str(reason);
    doc["relay"] = relay_state;
    doc["state"] = channel_state_to_str(state);
    doc["ts"] = timestamp_s;

    char payload[256];
    size_t len = serializeJson(doc, payload, sizeof(payload));
    mqtt_client.publish(topic_ack, (const uint8_t*)payload, len, false);
}

void mqtt_publish_event(
    const char* type,
    const char* severity,
    uint8_t channel,
    const char* message,
    uint32_t timestamp_s
) {
    if (!mqtt_client.connected()) return;

    JsonDocument doc;
    doc["schema"] = 1;
    doc["ts"] = timestamp_s;
    doc["type"] = type;
    doc["severity"] = severity;
    if (channel > 0) doc["ch"] = channel;
    doc["message"] = message;

    char payload[256];
    size_t len = serializeJson(doc, payload, sizeof(payload));
    mqtt_client.publish(topic_event, (const uint8_t*)payload, len, false);
}

void mqtt_publish_status(
    bool online,
    uint32_t uptime_s,
    int8_t rssi,
    uint32_t free_heap,
    uint16_t buffer_depth,
    uint32_t dropped_total,
    const ProtectionOutput* out1,
    const ProtectionOutput* out2,
    const char* reason
) {
    if (!mqtt_client.connected()) return;

    JsonDocument doc;
    doc["schema"] = 1;
    doc["online"] = online;
    doc["device_id"] = current_device_id;
    doc["fw"] = "1.0.0";
    doc["uptime_s"] = uptime_s;
    doc["rssi"] = rssi;
    doc["free_heap"] = free_heap;
    doc["buffer_depth"] = buffer_depth;
    doc["dropped_total"] = dropped_total;
    doc["reason"] = reason ? reason : "periodic";

    JsonArray chs = doc["channels"].to<JsonArray>();
    if (out1) {
        JsonObject c1 = chs.add<JsonObject>();
        c1["ch"] = 1;
        c1["relay"] = out1->relay_commanded;
        c1["state"] = channel_state_to_str(out1->state);
    }
    if (out2) {
        JsonObject c2 = chs.add<JsonObject>();
        c2["ch"] = 2;
        c2["relay"] = out2->relay_commanded;
        c2["state"] = channel_state_to_str(out2->state);
    }

    char payload[512];
    size_t len = serializeJson(doc, payload, sizeof(payload));
    mqtt_client.publish(topic_status, (const uint8_t*)payload, len, true); // Retained!
}

void mqtt_drain_offline_buffer(OfflineBuffer* buffer) {
    if (!buffer || !mqtt_client.connected()) return;

    // Rate-limit buffer drain to 10 packets per cycle so we don't starve live telemetry
    int drained = 0;
    BufferedTelemetryItem item;

    while (drained < 10 && offline_buffer_pop(buffer, &item)) {
        ElectricalReading r;
        r.voltage_v = item.voltage_v;
        r.current_a = item.current_a;
        r.active_power_w = item.active_power_w;
        r.energy_kwh = item.energy_kwh;
        r.power_factor = item.power_factor;
        r.frequency_hz = item.frequency_hz;
        r.valid = true;
        r.timestamp_s = item.timestamp_s;

        mqtt_publish_telemetry(item.channel, &r, item.relay, item.state, true, item.clock_synced);
        drained++;
    }
}

#else
// Stub definitions for native compilation
void mqtt_manager_init(const char* device_id, CommandHandlerCallback cmd_cb) { (void)device_id; (void)cmd_cb; }
void mqtt_manager_set_credentials(const char* s, const char* p, const char* h, uint16_t port) { (void)s; (void)p; (void)h; (void)port; }
bool mqtt_manager_loop(uint32_t now_ms) { (void)now_ms; return false; }
bool mqtt_manager_is_connected(void) { return false; }
void mqtt_publish_telemetry(uint8_t c, const ElectricalReading* r, bool l, ChannelState s, bool b, bool cl) { (void)c; (void)r; (void)l; (void)s; (void)b; (void)cl; }
void mqtt_publish_ack(const char* id, uint8_t c, CommandResult res, CommandReason rea, bool l, ChannelState s, uint32_t t) { (void)id; (void)c; (void)res; (void)rea; (void)l; (void)s; (void)t; }
void mqtt_publish_event(const char* t, const char* s, uint8_t c, const char* m, uint32_t ts) { (void)t; (void)s; (void)c; (void)m; (void)ts; }
void mqtt_publish_status(bool o, uint32_t u, int8_t r, uint32_t f, uint16_t b, uint32_t d, const ProtectionOutput* o1, const ProtectionOutput* o2, const char* re) { (void)o; (void)u; (void)r; (void)f; (void)b; (void)d; (void)o1; (void)o2; (void)re; }
void mqtt_drain_offline_buffer(OfflineBuffer* buffer) { (void)buffer; }
#endif

