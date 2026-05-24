#include "sme_envelope.h"

#include "cJSON.h"

static cJSON *device_block(const sme_reading_t *r)
{
    cJSON *device = cJSON_CreateObject();
    cJSON_AddStringToObject(device, "id", r->device_id);
    cJSON_AddStringToObject(device, "model", r->model);

    cJSON *firmware = cJSON_AddObjectToObject(device, "firmware");
    cJSON_AddStringToObject(firmware, "version", r->fw_version);
    cJSON_AddStringToObject(firmware, "channel", r->fw_channel);

    cJSON *fleet = cJSON_AddObjectToObject(device, "fleet");
    cJSON_AddStringToObject(fleet, "id", r->fleet_id);
    cJSON_AddStringToObject(fleet, "tenant", r->fleet_tenant);
    return device;
}

static void add_metric(cJSON *arr, const char *name, const char *kind,
                       double value, const char *unit)
{
    cJSON *metric = cJSON_CreateObject();
    cJSON_AddStringToObject(metric, "name", name);
    cJSON_AddStringToObject(metric, "kind", kind);
    cJSON_AddNumberToObject(metric, "value", value);
    cJSON_AddStringToObject(metric, "unit", unit);
    cJSON_AddItemToArray(arr, metric);
}

char *sme_envelope_build(const sme_reading_t *r)
{
    cJSON *root = cJSON_CreateObject();
    cJSON_AddNumberToObject(root, "v", 1);
    cJSON_AddItemToObject(root, "device", device_block(r));
    cJSON_AddNumberToObject(root, "ts_ms", (double)r->ts_ms);
    cJSON_AddStringToObject(root, "ts_source", r->ts_source);

    if (r->traceparent) {
        cJSON *trace = cJSON_AddObjectToObject(root, "trace");
        cJSON_AddStringToObject(trace, "traceparent", r->traceparent);
    }

    cJSON *metrics = cJSON_AddArrayToObject(root, "metrics");
    add_metric(metrics, "mcu.cpu.temp_c", "gauge", r->cpu_temp_c, "Cel");
    add_metric(metrics, "mcu.uptime", "counter", (double)r->uptime_s, "s");
    add_metric(metrics, "mcu.synthetic.sine", "gauge", r->sine, "1");

    if (r->wifi_reconnect) {
        cJSON *events = cJSON_AddArrayToObject(root, "events");
        cJSON *event = cJSON_CreateObject();
        cJSON_AddStringToObject(event, "name", "wifi.reconnect");
        cJSON_AddStringToObject(event, "severity", "warn");
        cJSON *attrs = cJSON_AddObjectToObject(event, "attrs");
        cJSON_AddNumberToObject(attrs, "rssi", r->rssi);
        cJSON_AddItemToArray(events, event);
    }

    char *out = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    return out;
}

char *sme_offline_build(const char *device_id, const char *fleet_id)
{
    cJSON *root = cJSON_CreateObject();
    cJSON_AddNumberToObject(root, "v", 1);
    cJSON *device = cJSON_AddObjectToObject(root, "device");
    cJSON_AddStringToObject(device, "id", device_id);
    cJSON *fleet = cJSON_AddObjectToObject(device, "fleet");
    cJSON_AddStringToObject(fleet, "id", fleet_id);
    cJSON_AddStringToObject(root, "reason", "lwt");

    char *out = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    return out;
}
