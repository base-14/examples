#include "traceparent.h"

#include <stdint.h>
#include <stdio.h>

#include "esp_random.h"

static void to_hex(char *dst, const uint8_t *src, size_t n)
{
    static const char digits[] = "0123456789abcdef";
    for (size_t i = 0; i < n; i++) {
        dst[i * 2] = digits[src[i] >> 4];
        dst[i * 2 + 1] = digits[src[i] & 0x0f];
    }
}

void traceparent_generate(char *out, size_t len)
{
    uint8_t trace_id[16];
    uint8_t span_id[8];
    esp_fill_random(trace_id, sizeof(trace_id));
    esp_fill_random(span_id, sizeof(span_id));

    char tid[33];
    char sid[17];
    to_hex(tid, trace_id, sizeof(trace_id));
    tid[32] = '\0';
    to_hex(sid, span_id, sizeof(span_id));
    sid[16] = '\0';

    snprintf(out, len, "00-%s-%s-01", tid, sid);
}
