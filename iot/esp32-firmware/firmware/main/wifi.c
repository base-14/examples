#include "wifi.h"

#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "sdkconfig.h"

static const char *TAG = "wifi";
static EventGroupHandle_t s_events;
static const int CONNECTED_BIT = BIT0;

static bool s_seen_first_connect;
static volatile bool s_reconnected;

static void on_wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_events, CONNECTED_BIT);
        if (s_seen_first_connect) {
            s_reconnected = true;  // a real drop, not the initial connect
        }
        ESP_LOGW(TAG, "disconnected; reconnecting");
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        s_seen_first_connect = true;
        xEventGroupSetBits(s_events, CONNECTED_BIT);
        ESP_LOGI(TAG, "connected");
    }
}

void wifi_init_sta(void)
{
    s_events = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &on_wifi_event, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &on_wifi_event, NULL, NULL));

    wifi_config_t wifi_config = {0};
    strncpy((char *)wifi_config.sta.ssid, CONFIG_WIFI_SSID,
            sizeof(wifi_config.sta.ssid) - 1);
    strncpy((char *)wifi_config.sta.password, CONFIG_WIFI_PASSWORD,
            sizeof(wifi_config.sta.password) - 1);

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "connecting to \"%s\"", CONFIG_WIFI_SSID);
    xEventGroupWaitBits(s_events, CONNECTED_BIT, pdFALSE, pdTRUE, portMAX_DELAY);
}

bool wifi_is_connected(void)
{
    return (xEventGroupGetBits(s_events) & CONNECTED_BIT) != 0;
}

bool wifi_take_reconnect(void)
{
    if (s_reconnected) {
        s_reconnected = false;
        return true;
    }
    return false;
}

int wifi_rssi(void)
{
    int rssi = 0;
    if (esp_wifi_sta_get_rssi(&rssi) != ESP_OK) {
        return 0;
    }
    return rssi;
}
