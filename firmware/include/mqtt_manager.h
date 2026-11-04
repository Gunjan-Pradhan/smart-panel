#ifndef MQTT_MANAGER_H
#define MQTT_MANAGER_H

#include <stdbool.h>
#include <stdint.h>
#include "protection_types.h"
#include "offline_buffer.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*CommandHandlerCallback)(
    const char* cmd_id,
    uint8_t channel,
    const char* action,
    uint32_t issued_at,
    uint32_t expires_at,
    const char* source
);

void mqtt_manager_init(const char* device_id, CommandHandlerCallback cmd_cb);
void mqtt_manager_set_credentials(const char* ssid, const char* pass, const char* host, uint16_t port);
bool mqtt_manager_loop(uint32_t now_ms);
bool mqtt_manager_is_connected(void);

void mqtt_publish_telemetry(
    uint8_t channel,
    const ElectricalReading* reading,
    bool relay_state,
    ChannelState state,
    bool buffered,
    bool clock_synced
);

void mqtt_publish_ack(
    const char* cmd_id,
    uint8_t channel,
    CommandResult result,
    CommandReason reason,
    bool relay_state,
    ChannelState state,
    uint32_t timestamp_s
);

void mqtt_publish_event(
    const char* type,
    const char* severity,
    uint8_t channel,
    const char* message,
    uint32_t timestamp_s
);

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
);

void mqtt_drain_offline_buffer(OfflineBuffer* buffer);

#ifdef __cplusplus
}
#endif

#endif // MQTT_MANAGER_H

