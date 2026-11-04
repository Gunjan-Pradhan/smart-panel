#ifndef NVS_MANAGER_H
#define NVS_MANAGER_H

#include <stdbool.h>
#include <stdint.h>
#include "protection_types.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    char wifi_ssid[32];
    char wifi_pass[64];
    char mqtt_host[64];
    uint16_t mqtt_port;
    char device_id[32];
} NetworkSettings;

typedef struct {
    bool enabled;
    uint8_t days_of_week; // bitmask 1..127
    uint8_t on_hour;
    uint8_t on_min;
    uint8_t off_hour;
    uint8_t off_min;
} LocalSchedule;

void nvs_manager_init(void);
bool nvs_load_limits(uint8_t channel, ChannelLimits* out_limits);
bool nvs_save_limits(uint8_t channel, const ChannelLimits* limits);
bool nvs_load_network_settings(NetworkSettings* out_settings);
bool nvs_save_network_settings(const NetworkSettings* settings);
bool nvs_load_schedule(uint8_t channel, LocalSchedule* out_schedule);
bool nvs_save_schedule(uint8_t channel, const LocalSchedule* schedule);
void nvs_reset_defaults(void);

#ifdef __cplusplus
}
#endif

#endif // NVS_MANAGER_H

