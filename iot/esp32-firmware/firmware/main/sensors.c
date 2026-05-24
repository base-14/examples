#include "sensors.h"

#include <math.h>

#include "driver/temperature_sensor.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "sensors";
static temperature_sensor_handle_t s_tsens;

void sensors_init(void)
{
    temperature_sensor_config_t cfg = TEMPERATURE_SENSOR_CONFIG_DEFAULT(10, 50);
    ESP_ERROR_CHECK(temperature_sensor_install(&cfg, &s_tsens));
    ESP_ERROR_CHECK(temperature_sensor_enable(s_tsens));
    ESP_LOGI(TAG, "temperature sensor ready");
}

int64_t sensors_uptime_s(void)
{
    return esp_timer_get_time() / 1000000;
}

float sensors_cpu_temp_c(void)
{
    float celsius = 0;
    if (temperature_sensor_get_celsius(s_tsens, &celsius) != ESP_OK) {
        ESP_LOGW(TAG, "temperature read failed");
        return -1;
    }
    return celsius;
}

double sensors_sine(void)
{
    return sin((double)sensors_uptime_s() / 15.0);
}
