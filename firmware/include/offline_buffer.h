#ifndef OFFLINE_BUFFER_H
#define OFFLINE_BUFFER_H

#include <stdint.h>
#include <stdbool.h>
#include "protection_types.h"

#ifdef __cplusplus
extern "C" {
#endif

#define OFFLINE_BUFFER_CAPACITY 256

typedef struct {
    uint8_t channel;
    uint32_t timestamp_s;
    float voltage_v;
    float current_a;
    float active_power_w;
    float energy_kwh;
    float power_factor;
    float frequency_hz;
    bool relay;
    ChannelState state;
    bool clock_synced;
} BufferedTelemetryItem;

typedef struct {
    BufferedTelemetryItem items[OFFLINE_BUFFER_CAPACITY];
    uint16_t head;
    uint16_t tail;
    uint16_t count;
    uint32_t dropped_total;
} OfflineBuffer;

void offline_buffer_init(OfflineBuffer* buf);
bool offline_buffer_push(OfflineBuffer* buf, const BufferedTelemetryItem* item);
bool offline_buffer_pop(OfflineBuffer* buf, BufferedTelemetryItem* out_item);
uint16_t offline_buffer_count(const OfflineBuffer* buf);
uint32_t offline_buffer_dropped_total(const OfflineBuffer* buf);
bool offline_buffer_is_empty(const OfflineBuffer* buf);

#ifdef __cplusplus
}
#endif

#endif // OFFLINE_BUFFER_H

