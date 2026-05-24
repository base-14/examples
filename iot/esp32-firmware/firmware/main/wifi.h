#pragma once

#include <stdbool.h>

// Start Wi-Fi in station mode with auto-reconnect, then block until the first
// IP is acquired (so trace IDs and SNTP have a live RF subsystem to rely on).
void wifi_init_sta(void);

bool wifi_is_connected(void);

// Returns true at most once per reconnect: true if the link dropped and came
// back since the last call, so the next envelope can carry a wifi.reconnect
// event. Clears the flag.
bool wifi_take_reconnect(void);

// Current AP RSSI in dBm, or 0 if unavailable.
int wifi_rssi(void);
