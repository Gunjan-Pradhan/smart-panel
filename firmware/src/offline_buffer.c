#include "offline_buffer.h"

void offline_buffer_init(OfflineBuffer* buf) {
    if (!buf) return;
    buf->head = 0;
    buf->tail = 0;
    buf->count = 0;
    buf->dropped_total = 0;
}

bool offline_buffer_push(OfflineBuffer* buf, const BufferedTelemetryItem* item) {
    if (!buf || !item) return false;

    if (buf->count >= OFFLINE_BUFFER_CAPACITY) {
        // Buffer is full: overwrite oldest item (advance tail) and count drop
        buf->tail = (buf->tail + 1) % OFFLINE_BUFFER_CAPACITY;
        buf->count--;
        buf->dropped_total++;
    }

    buf->items[buf->head] = *item;
    buf->head = (buf->head + 1) % OFFLINE_BUFFER_CAPACITY;
    buf->count++;
    return true;
}

bool offline_buffer_pop(OfflineBuffer* buf, BufferedTelemetryItem* out_item) {
    if (!buf || buf->count == 0 || !out_item) return false;

    *out_item = buf->items[buf->tail];
    buf->tail = (buf->tail + 1) % OFFLINE_BUFFER_CAPACITY;
    buf->count--;
    return true;
}

uint16_t offline_buffer_count(const OfflineBuffer* buf) {
    return buf ? buf->count : 0;
}

uint32_t offline_buffer_dropped_total(const OfflineBuffer* buf) {
    return buf ? buf->dropped_total : 0;
}

bool offline_buffer_is_empty(const OfflineBuffer* buf) {
    return buf ? (buf->count == 0) : true;
}

