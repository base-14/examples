#pragma once

#include <stddef.h>

// Buffer size for a W3C traceparent string: "00-" + 32 hex + "-" + 16 hex +
// "-01" + NUL.
#define TRACEPARENT_LEN 56

// Write a W3C traceparent (version 00, sampled) into out. trace_id and span_id
// are filled from esp_fill_random(), which is a CSPRNG once the RF subsystem is
// up - so call this only after Wi-Fi connects.
void traceparent_generate(char *out, size_t len);
