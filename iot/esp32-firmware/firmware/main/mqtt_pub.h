#pragma once

#include <stdbool.h>

// Wrapper over the esp-mqtt component. Named mqtt_pub to avoid colliding with
// esp-mqtt's own public header, mqtt_client.h.

// Start the MQTT 5 client and connect to uri, registering a Last Will so the
// broker publishes lwt_payload to lwt_topic on an ungraceful disconnect.
// lwt_topic and lwt_payload must outlive the client (pass static/heap strings).
void mqtt_app_start(const char *uri, const char *lwt_topic, const char *lwt_payload);

bool mqtt_is_connected(void);

// Publish payload to topic at the given QoS. Returns the message id, or -1.
int mqtt_publish(const char *topic, const char *payload, int qos);
