#include "mqtt_pub.h"

#include "esp_log.h"
#include "mqtt_client.h"  // esp-mqtt component

static const char *TAG = "mqtt";
static esp_mqtt_client_handle_t s_client;
static volatile bool s_connected;

static void on_mqtt_event(void *args, esp_event_base_t base, int32_t id, void *data)
{
    switch ((esp_mqtt_event_id_t)id) {
    case MQTT_EVENT_CONNECTED:
        s_connected = true;
        ESP_LOGI(TAG, "connected to broker");
        break;
    case MQTT_EVENT_DISCONNECTED:
        s_connected = false;
        ESP_LOGW(TAG, "disconnected from broker");
        break;
    case MQTT_EVENT_ERROR:
        ESP_LOGW(TAG, "mqtt error");
        break;
    default:
        break;
    }
}

void mqtt_app_start(const char *uri, const char *lwt_topic, const char *lwt_payload)
{
    esp_mqtt_client_config_t cfg = {
        .broker.address.uri = uri,
        .session.protocol_ver = MQTT_PROTOCOL_V_5,
        .session.last_will = {
            .topic = lwt_topic,
            .msg = lwt_payload,
            .qos = 1,
            .retain = false,
        },
    };

    s_client = esp_mqtt_client_init(&cfg);
    esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID, &on_mqtt_event, NULL);
    esp_mqtt_client_start(s_client);
    ESP_LOGI(TAG, "client started for %s", uri);
}

bool mqtt_is_connected(void)
{
    return s_connected;
}

int mqtt_publish(const char *topic, const char *payload, int qos)
{
    if (!s_connected) {
        return -1;
    }
    return esp_mqtt_client_publish(s_client, topic, payload, 0, qos, 0);
}
