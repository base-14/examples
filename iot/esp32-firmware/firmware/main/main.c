#include <stdlib.h>
#include <string.h>
#include <sys/time.h>

#include "esp_log.h"
#include "esp_netif_sntp.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#include "mqtt_pub.h"
#include "sensors.h"
#include "sme_envelope.h"
#include "traceparent.h"
#include "wifi.h"

static const char *TAG = "mcu";

static void init_nvs(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
}

static bool sync_time(void)
{
    esp_sntp_config_t cfg = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    esp_netif_sntp_init(&cfg);
    if (esp_netif_sntp_sync_wait(pdMS_TO_TICKS(10000)) == ESP_OK) {
        ESP_LOGI(TAG, "time synced via SNTP");
        return true;
    }
    ESP_LOGW(TAG, "SNTP not synced; falling back to the uptime clock");
    return false;
}

void app_main(void)
{
    init_nvs();
    sensors_init();
    wifi_init_sta();  // blocks until the first IP, so RF (esp_random/SNTP) is up

    bool time_synced = sync_time();

    static char telemetry_topic[160];
    static char offline_topic[160];
    snprintf(telemetry_topic, sizeof(telemetry_topic), "%s/%s/telemetry",
             CONFIG_MQTT_TOPIC_PREFIX, CONFIG_DEVICE_ID);
    snprintf(offline_topic, sizeof(offline_topic), "%s/%s/offline",
             CONFIG_MQTT_TOPIC_PREFIX, CONFIG_DEVICE_ID);

    // The Last Will must outlive the client, so this lives for the program.
    char *lwt = sme_offline_build(CONFIG_DEVICE_ID, CONFIG_FLEET_ID);
    mqtt_app_start(CONFIG_MQTT_BROKER_URI, offline_topic, lwt);

    while (true) {
        int64_t ts_ms;
        const char *ts_source;
        if (time_synced) {
            struct timeval tv;
            gettimeofday(&tv, NULL);
            ts_ms = (int64_t)tv.tv_sec * 1000 + tv.tv_usec / 1000;
            ts_source = "sntp";
        } else {
            ts_ms = esp_timer_get_time() / 1000;
            ts_source = "uptime";
        }

        char traceparent[TRACEPARENT_LEN];
        traceparent_generate(traceparent, sizeof(traceparent));

        sme_reading_t reading = {
            .device_id = CONFIG_DEVICE_ID,
            .model = CONFIG_DEVICE_MODEL,
            .fw_version = CONFIG_FIRMWARE_VERSION,
            .fw_channel = CONFIG_FIRMWARE_CHANNEL,
            .fleet_id = CONFIG_FLEET_ID,
            .fleet_tenant = CONFIG_FLEET_TENANT,
            .ts_ms = ts_ms,
            .ts_source = ts_source,
            .traceparent = traceparent,
            .cpu_temp_c = sensors_cpu_temp_c(),
            .uptime_s = sensors_uptime_s(),
            .sine = sensors_sine(),
            .wifi_reconnect = wifi_take_reconnect(),
            .rssi = wifi_rssi(),
        };

        char *json = sme_envelope_build(&reading);
        if (json) {
            int mid = mqtt_publish(telemetry_topic, json, 1);
            ESP_LOGI(TAG, "published %d bytes, mid=%d", (int)strlen(json), mid);
            free(json);
        }

        vTaskDelay(pdMS_TO_TICKS(CONFIG_PUBLISH_INTERVAL_S * 1000));
    }
}
