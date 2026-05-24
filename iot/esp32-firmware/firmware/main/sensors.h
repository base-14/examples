#pragma once

#include <stdint.h>

// Install and enable the on-chip temperature sensor. Call once at boot.
void sensors_init(void);

// Seconds since boot.
int64_t sensors_uptime_s(void);

// On-chip temperature in Celsius. Returns -1 on read failure.
float sensors_cpu_temp_c(void);

// A synthetic oscillating value (sine of uptime), so charts move without an
// external peripheral and the Wokwi simulation stays friction-free.
double sensors_sine(void);
