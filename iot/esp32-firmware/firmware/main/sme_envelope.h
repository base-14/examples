#pragma once

#include <stdbool.h>
#include <stdint.h>

// One reading's worth of data, turned into an SME-v1 JSON envelope.
typedef struct {
    const char *device_id;
    const char *model;
    const char *fw_version;
    const char *fw_channel;
    const char *fleet_id;
    const char *fleet_tenant;
    int64_t ts_ms;
    const char *ts_source;     // "sntp" or "uptime"
    const char *traceparent;   // NULL to omit the trace block
    float cpu_temp_c;
    int64_t uptime_s;
    double sine;
    bool wifi_reconnect;       // include a wifi.reconnect event when true
    int rssi;
} sme_reading_t;

// Build the SME-v1 telemetry JSON. Caller frees the result with free().
char *sme_envelope_build(const sme_reading_t *reading);

// Build the small offline (Last Will) JSON. Caller frees with free().
char *sme_offline_build(const char *device_id, const char *fleet_id);
