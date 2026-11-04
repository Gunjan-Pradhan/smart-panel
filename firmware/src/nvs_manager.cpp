#include "nvs_manager.h"
#include <string.h>

#ifdef ARDUINO
#include <Preferences.h>
static Preferences prefs;
#endif

void nvs_manager_init(void) {
    // Initialized on demand via Preferences namespaces
}

bool nvs_load_limits(uint8_t channel, ChannelLimits* out_limits) {
    if (!out_limits) return false;

#ifdef ARDUINO
    char ns[16];
    snprintf(ns, sizeof(ns), "limits_ch%u", channel);
    if (!prefs.begin(ns, true)) return false;

    out_limits->confirmed_current_a = prefs.getFloat("cur_a", 0.0f);
    out_limits->confirmed_power_w = prefs.getFloat("pow_w", 0.0f);
    out_limits->confirmed_min_pf = prefs.getFloat("min_pf", 0.0f);
    out_limits->inrush_blanking_ms = prefs.getUInt("inrush_ms", (channel == 1) ? 2000 : 50);
    out_limits->retry_delay_ms = prefs.getUInt("retry_ms", 10000);
    out_limits->trip_debounce_ms = prefs.getUInt("deb_ms", 150);
    out_limits->max_retry_strikes = (uint8_t)prefs.getUChar("strikes", 3);

    prefs.end();
    return true;
#else
    return false;
#endif
}

bool nvs_save_limits(uint8_t channel, const ChannelLimits* limits) {
    if (!limits) return false;

#ifdef ARDUINO
    char ns[16];
    snprintf(ns, sizeof(ns), "limits_ch%u", channel);
    if (!prefs.begin(ns, false)) return false;

    prefs.putFloat("cur_a", limits->confirmed_current_a);
    prefs.putFloat("pow_w", limits->confirmed_power_w);
    prefs.putFloat("min_pf", limits->confirmed_min_pf);
    prefs.putUInt("inrush_ms", limits->inrush_blanking_ms);
    prefs.putUInt("retry_ms", limits->retry_delay_ms);
    prefs.putUInt("deb_ms", limits->trip_debounce_ms);
    prefs.putUChar("strikes", limits->max_retry_strikes);

    prefs.end();
    return true;
#else
    return false;
#endif
}

bool nvs_load_network_settings(NetworkSettings* out_settings) {
    if (!out_settings) return false;

#ifdef ARDUINO
    if (!prefs.begin("network", true)) return false;

    String ssid = prefs.getString("ssid", "SmartPanel_AP");
    String pass = prefs.getString("pass", "protection2026");
    String host = prefs.getString("host", "127.0.0.1");
    uint16_t port = prefs.getUShort("port", 1883);
    String dev_id = prefs.getString("dev_id", "PANEL-0001");

    strncpy(out_settings->wifi_ssid, ssid.c_str(), sizeof(out_settings->wifi_ssid) - 1);
    strncpy(out_settings->wifi_pass, pass.c_str(), sizeof(out_settings->wifi_pass) - 1);
    strncpy(out_settings->mqtt_host, host.c_str(), sizeof(out_settings->mqtt_host) - 1);
    out_settings->mqtt_port = port;
    strncpy(out_settings->device_id, dev_id.c_str(), sizeof(out_settings->device_id) - 1);

    prefs.end();
    return true;
#else
    return false;
#endif
}

bool nvs_save_network_settings(const NetworkSettings* settings) {
    if (!settings) return false;

#ifdef ARDUINO
    if (!prefs.begin("network", false)) return false;

    prefs.putString("ssid", settings->wifi_ssid);
    prefs.putString("pass", settings->wifi_pass);
    prefs.putString("host", settings->mqtt_host);
    prefs.putUShort("port", settings->mqtt_port);
    prefs.putString("dev_id", settings->device_id);

    prefs.end();
    return true;
#else
    return false;
#endif
}

bool nvs_load_schedule(uint8_t channel, LocalSchedule* out_schedule) {
    if (!out_schedule) return false;

#ifdef ARDUINO
    char ns[16];
    snprintf(ns, sizeof(ns), "sched_ch%u", channel);
    if (!prefs.begin(ns, true)) return false;

    out_schedule->enabled = prefs.getBool("en", false);
    out_schedule->days_of_week = prefs.getUChar("days", 0);
    out_schedule->on_hour = prefs.getUChar("on_h", 0);
    out_schedule->on_min = prefs.getUChar("on_m", 0);
    out_schedule->off_hour = prefs.getUChar("off_h", 0);
    out_schedule->off_min = prefs.getUChar("off_m", 0);

    prefs.end();
    return true;
#else
    return false;
#endif
}

bool nvs_save_schedule(uint8_t channel, const LocalSchedule* schedule) {
    if (!schedule) return false;

#ifdef ARDUINO
    char ns[16];
    snprintf(ns, sizeof(ns), "sched_ch%u", channel);
    if (!prefs.begin(ns, false)) return false;

    prefs.putBool("en", schedule->enabled);
    prefs.putUChar("days", schedule->days_of_week);
    prefs.putUChar("on_h", schedule->on_hour);
    prefs.putUChar("on_m", schedule->on_min);
    prefs.putUChar("off_h", schedule->off_hour);
    prefs.putUChar("off_m", schedule->off_min);

    prefs.end();
    return true;
#else
    return false;
#endif
}

void nvs_reset_defaults(void) {
#ifdef ARDUINO
    prefs.begin("limits_ch1", false); prefs.clear(); prefs.end();
    prefs.begin("limits_ch2", false); prefs.clear(); prefs.end();
    prefs.begin("network", false); prefs.clear(); prefs.end();
    prefs.begin("sched_ch1", false); prefs.clear(); prefs.end();
    prefs.begin("sched_ch2", false); prefs.clear(); prefs.end();
#endif
}

