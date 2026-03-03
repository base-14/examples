# Telemetry Signal Reference

Complete inventory of all OpenTelemetry signals emitted by the Astronomy Shop
Mobile app. All signals are exported via OTLP/HTTP to the configured collector.

---

## 1. Resource Attributes

Attached to every trace, metric, and log export.

| Attribute | Source | Example |
|-----------|--------|---------|
| `service.name` | `.env` SERVICE_NAME | `astronomy-shop-mobile` |
| `service.version` | `.env` SERVICE_VERSION | `0.0.1` |
| `deployment.environment` | `.env` ENVIRONMENT | `development` |
| `telemetry.sdk.name` | Hardcoded | `flutter-opentelemetry` |
| `telemetry.sdk.version` | Hardcoded | `0.18.10` |
| `session.id` | Generated (UUID v4) | `a3f1b2c4-...` |
| `app.build_id` | `.env` SERVICE_VERSION | `0.0.1` |
| `app.installation.id` | Persisted UUID (file) | `b7e2d1f3-...` |
| `os.name` | `dart:io` Platform | `macos`, `ios`, `android` |
| `os.version` | `dart:io` Platform | `Version 14.5 ...` |
| `device.locale` | `dart:io` Platform | `en_US` |
| `device.screen.width` | `dart:ui` PlatformDispatcher | `393` |
| `device.screen.height` | `dart:ui` PlatformDispatcher | `852` |
| `device.screen.density` | `dart:ui` PlatformDispatcher | `3.0` |
| `device.manufacturer` | `device_info_plus` (iOS/Android) | `Apple`, `Samsung` |
| `device.model.identifier` | `device_info_plus` (iOS/Android) | `iPhone15,2`, `SM-G920F` |
| `device.model.name` | `device_info_plus` (iOS/Android) | `iPhone`, `Galaxy S6` |

---

## 2. Traces

### 2.1 Span Overview

Three kinds of spans are emitted:

1. **Named spans** created via `tracer.startSpan()` — long-lived operations with
   start/end times and child events.
2. **Event spans** created via `TelemetryService.recordEvent()` — point-in-time
   business events sent as individual OTLP spans.
3. **HTTP client spans** created by `HttpService` — one per HTTP request with
   W3C `traceparent` propagation.

### 2.2 App Lifecycle & Session Spans

| Span Name | File | When |
|-----------|------|------|
| `app_initialization` | telemetry_service.dart | App startup |
| `app_shutdown` | telemetry_service.dart | App shutdown |
| `telemetry_batch` | telemetry_service.dart | Periodic batch flush (30s) |
| `error_event` | telemetry_service.dart | `TelemetryService.recordError()` |

Lifecycle transitions are now emitted as `device.app.lifecycle` events (see Section 3.15).

### 2.3 HTTP Client Spans

Span name: `{METHOD} {path}` (e.g. `GET /api/products`). Kind: `SPAN_KIND_CLIENT`.

| Attribute | Emitted |
|-----------|---------|
| `http.request.method` | Always |
| `url.full` | Always |
| `url.scheme` | Always |
| `url.path` | Always |
| `server.address` | Always |
| `server.port` | Always |
| `http.response.status_code` | On response |
| `http.response.body.size` | On response |
| `http.request.duration_ms` | Always |
| `error.type` | On status >= 400 or network error |

### 2.4 API Operation Spans

| Span Name | File | Context |
|-----------|------|---------|
| `products_api_get_all` | products_api_service.dart | Load product catalog |
| `products_api_get_single` | products_api_service.dart | Get one product by ID |
| `products_cache_clear` | products_api_service.dart | Clear product cache |
| `product_search` | search_service.dart | Search products |
| `recommendations_get` | recommendations_service.dart | Get recommendations |
| `recommendations_cache_clear` | recommendations_service.dart | Clear recommendations cache |

---

## 3. Events (via recordEvent)

Events are emitted as individual OTLP spans with point-in-time semantics.

### 3.1 Navigation & Screen Views

| Event | File | Key Attributes |
|-------|------|---------------|
| `screen_view` | main.dart, cart_screen, checkout_screen, search_screen, product_detail_screen, order_confirmation_screen | `app.screen.name`, plus screen-specific context (product_count, cart totals, etc.) |

Emitted from every screen's `initState`.

### 3.2 Product Interactions

| Event | File | Key Attributes |
|-------|------|---------------|
| `app.widget.click` | main.dart, search_screen, recommendations_section | `app.widget.id`, `app.widget.name`, `product_id`, `product_name`, `app.screen.name` |
| `product_load_error` | main.dart | `error_message`, `app.screen.name` |
| `product_refresh` | main.dart | `app.screen.name`, `current_product_count` |
| `app.widget.click` | product_detail_screen | `app.widget.id` (`share_button_{id}`), `app.widget.name` (`Share Product`), `product_id`, `product_name`, `app.screen.name` |

### 3.3 Cart Operations

| Event | File | Key Attributes |
|-------|------|---------------|
| `cart_initialize` | cart_service | `user_id` |
| `cart_add_item` | cart_service | `product_id`, `product_name`, `product_price`, `quantity` |
| `cart_add_item_error` | cart_service | `product_id`, `error_message` |
| `cart_update_quantity` | cart_service | `product_id`, `old_quantity`, `new_quantity` |
| `cart_update_error` | cart_service | `product_id`, `error_message` |
| `cart_remove_item` | cart_service | `product_id`, `quantity_removed` |
| `cart_remove_error` | cart_service | `product_id`, `error_message` |
| `cart_clear` | cart_service | `items_cleared` |
| `cart_clear_error` | cart_service | `error_message` |
| `cart_sync_success` | cart_service | `item_count`, `total_quantity`, `total_price`, `response_status` |
| `cart_sync_error` | cart_service | `error_message`, `item_count` |

### 3.4 Cart UI Interactions

| Event | File | Key Attributes |
|-------|------|---------------|
| `app.widget.click` | main.dart | `app.widget.id` (`cart_badge`), `app.widget.name`, `cart_item_count`, `cart_total_price` |
| `app.widget.click` | cart_screen | `app.widget.id` (`empty_cart_search_button`), `app.widget.name` (`search_button`) |
| `cart_quantity_change` | cart_screen | `product_id`, `old_quantity`, `new_quantity` |
| `cart_remove_item_ui` | cart_screen | `product_id`, `quantity_removed` |
| `cart_clear_initiated` | cart_screen | `items_count` |
| `cart_cleared_confirmed` | cart_screen | `cleared_items_count` |
| `checkout_initiated` | cart_screen | `cart_total_items`, `cart_total_price` |
| `continue_shopping` | cart_screen | — |

### 3.5 Checkout

| Event | File | Key Attributes |
|-------|------|---------------|
| `checkout_validation_failed` | checkout_screen | — |
| `checkout_place_order_started` | checkout_screen | `cart_item_count`, `cart_total_price`, `currency` |
| `checkout_place_order_success` | checkout_screen | `order_id`, `order_items_count`, `total_amount` |
| `checkout_place_order_failed` | checkout_screen | `error_message` |
| `checkout_place_order_exception` | checkout_screen | `error_message`, `error_type` |

### 3.6 Search

| Event | File | Key Attributes |
|-------|------|---------------|
| `app.widget.click` | main.dart | `app.widget.id` (`search_button`), `app.widget.name`, `app.screen.name` |
| `search_query_entered` | search_service | `query`, `query_length` |
| `search_result_clicked` | search_service | `product_id`, `search_query`, `result_position` |
| `search_no_results` | search_service | `query`, `query_length` |
| `search_metrics` | search_service | `query`, `results_count`, `search_duration_ms`, `data_source` |
| `search_error` | search_service | `query`, `error_message` |
| `search_cache_cleared` | search_service | — |

### 3.7 Recommendations

| Event | File | Key Attributes |
|-------|------|---------------|
| `recommendations_cart_based` | recommendations_service | `cart_items_count`, `product_ids` |
| `recommendation_clicked` | recommendations_service | `product_id`, `product_name`, `position` |
| `app.widget.click` | recommendations_section | `app.widget.id` (`recommendations_refresh`), `app.widget.name` (`refresh_button`) |
| `recommendations_viewed` | recommendations_service | `recommendations_count`, `product_ids` |
| `recommendations_metrics` | recommendations_service | `count`, `source`, `average_price`, `unique_categories` |

### 3.8 Currency

| Event | File | Key Attributes |
|-------|------|---------------|
| `currency_service_initialize` | currency_service | `default_currency` |
| `currency_supported_loaded` | currency_service | `currencies_count`, `currencies` |
| `currency_supported_error` | currency_service | `error_message`, `status_code` |
| `currency_load_exception` | currency_service | `error_message` |
| `currency_changed` | currency_service | `previous_currency`, `new_currency` |
| `currency_conversion_success` | currency_service | `from_currency`, `to_currency`, `conversion_rate` |
| `currency_conversion_error` | currency_service | `from_currency`, `to_currency`, `error_message` |
| `currency_conversion_exception` | currency_service | `from_currency`, `to_currency`, `error_message` |
| `currency_selector_changed` | currency_selector | `previous_currency`, `new_currency` |
| `currency_selector_dialog_opened` | currency_selector | `current_currency` |
| `currency_selector_dialog_cancelled` | currency_selector | `selected_currency` |
| `currency_selector_dialog_selected` | currency_selector | `previous_currency`, `new_currency` |

### 3.9 Conversion Funnel

| Event | File | Key Attributes |
|-------|------|---------------|
| `funnel_stage_transition` | funnel_tracking_service | `funnel.stage`, `funnel.stage_name`, `funnel.stage_order`, `funnel.is_progression`, `funnel.journey_type`, `funnel.time_in_previous_stage_ms` |
| `funnel_conversion` | funnel_tracking_service | `funnel.conversion_from`, `funnel.conversion_to`, `funnel.time_to_convert_ms` |
| `funnel_drop_off` | funnel_tracking_service | `funnel.drop_off_stage`, `funnel.drop_off_reason`, `funnel.journey_stages_completed` |
| `funnel_abandonment` | funnel_tracking_service | `funnel.abandonment_stage`, `funnel.time_in_stage_before_abandonment_ms` |

Funnel stages (in order): `product_list_view` → `product_detail_view` → `add_to_cart` → `cart_view` → `checkout_info_entered` → `payment_info_entered` → `order_placed` → `order_confirmed`.

### 3.10 Error & Crash

| Event | File | Key Attributes |
|-------|------|---------------|
| `error_occurred` | error_handler_service | `error.message`, `error.context`, `error.type`, `error.severity` (crash\|error), `error.is_fatal`, `session.duration_ms`, `app.screen.name`, `user.last_action`, `breadcrumbs` |
| `error_handler_initialize` | error_handler_service | `session_id` |
| `errors_cleared` | error_handler_service | `cleared_count` |
| `error_boundary_retry` | error_boundary | `context` |

### 3.11 Performance & Monitoring

| Event | File | Key Attributes |
|-------|------|---------------|
| `performance_service_initialize` | performance_service | `session_id` |
| `performance_metric` | performance_service | `operation_name`, `duration_ms` |
| `memory_usage` | performance_service | `estimated_memory_mb`, `metrics_count` |
| `app.jank` | performance_service | `average_fps`, `app.jank.frame_count`, `app.screen.name` |
| `slow_operation_detected` | performance_service | `operation_name`, `duration_ms`, `severity` |

### 3.12 Image Cache

| Event | File | Key Attributes |
|-------|------|---------------|
| `image_cache_battery_skip` | image_cache_service | `url`, `battery_level` |
| `image_cache_hit` | image_cache_service | `cache_type` (memory\|disk), `url`, `size_bytes` |
| `image_cache_download` | image_cache_service | `url`, `size_bytes`, `battery_level` |
| `image_cache_error` | image_cache_service | `url`, `error` |
| `image_cache_cleared` | image_cache_service | `cache_type` (memory\|disk) |

### 3.13 Telemetry System

| Event | File | Key Attributes |
|-------|------|---------------|
| `telemetry_sampling_rate_changed` | telemetry_service | `old_sampling_rate`, `new_sampling_rate`, `battery_level` |
| `telemetry_batch_error` | telemetry_service | `error`, `batch_size` |

### 3.14 Session & Lifecycle Events

| Event | File | Key Attributes |
|-------|------|---------------|
| `session.start` | telemetry_service | `session.id` |
| `session.end` | telemetry_service | `session.id`, `session.duration_ms` |
| `device.app.lifecycle` | app_lifecycle_observer | `ios.app.state` or `android.app.state`, `session.id` |

`device.app.lifecycle` uses platform-specific state attributes:
- **iOS** (`ios.app.state`): `active`, `inactive`, `background`, `terminate`
- **Android** (`android.app.state`): `foreground`, `created`, `background`

### 3.15 Debug (kDebugMode only)

| Event | File | Key Attributes |
|-------|------|---------------|
| `performance_debug_screen_opened` | performance_debug_screen | — |
| `performance_test_start` | performance_debug_screen | `event_type` |
| `performance_test_complete` | performance_debug_screen | `event_type`, `event_count`, `total_duration_ms` |

---

## 4. Metrics

Exported to `$OTLP_ENDPOINT/$OTLP_METRICS_EXPORTER` every 60 seconds.

### 4.1 HTTP Metrics

| Metric | Type | Attributes | Source |
|--------|------|-----------|--------|
| `http.client.request.duration` | Histogram (ms) | `http.request.method`, `server.address` | http_service.dart |
| `http.client.request.count` | Counter | `http.request.method`, `http.response.status_code` | http_service.dart |

Histogram bounds: `[5, 10, 25, 50, 75, 100, 250, 500, 1000, 2500, 5000, 10000]`

### 4.2 Error Metrics

| Metric | Type | Attributes | Source |
|--------|------|-----------|--------|
| `app.error.count` | Counter | `error.type`, `app.screen.name` | error_handler_service.dart |
| `app.crash.count` | Counter | `error.type`, `app.screen.name` | error_handler_service.dart |

### 4.3 Session Metrics

| Metric | Type | Attributes | Source |
|--------|------|-----------|--------|
| `app.session.count` | Counter | `crash_free` (`true`\|`false`) | error_handler_service.dart |

Emitted once at session end (via `TelemetryService.shutdown()`).

---

## 5. Structured Logs

Exported to `$OTLP_ENDPOINT/$OTLP_LOGS_EXPORTER` every 30 seconds (100-record
buffer). Fatal logs trigger an immediate flush.

### 5.1 Severity Levels

| Level | OTLP Number | Sampling | Behavior |
|-------|------------|----------|----------|
| DEBUG | 5 | Battery-aware | Skipped when battery low |
| INFO | 9 | Battery-aware | Skipped when battery low |
| WARN | 13 | Always sent | — |
| ERROR | 17 | Always sent | Includes stack trace (max 4000 chars) |
| FATAL | 21 | Always sent | Includes stack trace + force-flushes all signals |

### 5.2 Log Messages

| Severity | Pattern | Source | When |
|----------|---------|--------|------|
| WARN | `HTTP {method} {uri} returned {status}` | http_service.dart | 4xx HTTP responses |
| ERROR | `HTTP {method} {uri} returned {status}` | http_service.dart | 5xx HTTP responses |
| ERROR | `HTTP {method} {uri} failed: {exception}` | http_service.dart | Network/connection failures |
| ERROR | `{error message}` | error_handler_service.dart | Non-fatal handled errors (ErrorBoundary catches, custom errors) |
| FATAL | `{error message}` | error_handler_service.dart | Crashes (unhandled Flutter errors, platform errors, zone errors) |

### 5.3 Log Attributes

All error/fatal logs from `ErrorHandlerService` include:

| Attribute | Description |
|-----------|-------------|
| `error.message` | Error string |
| `error.context` | Where the error occurred |
| `error.type` | `flutter_error`, `platform_error`, `zone_uncaught_error`, `custom_error` |
| `error.severity` | `crash` or `error` |
| `error.is_fatal` | `true` or `false` |
| `session.id` | Session UUID |
| `session.duration_ms` | Time since session start |
| `app.screen.name` | Screen where error occurred |
| `user.last_action` | Last breadcrumb |
| `breadcrumbs` | Last 20 user actions joined by ` > ` |
| `has_stack_trace` | Whether stack trace is present |

HTTP error logs include `http.request.method`, `url.full`,
`http.response.status_code`, and `duration_ms`.

### 5.4 Log-to-Trace Correlation

`warn` and `error` level logs accept optional `traceId` and `spanId` fields for
linking log records to spans in the trace backend.

---

## 6. Error Classification

| Error Source | Severity | Type | Fatal |
|-------------|----------|------|-------|
| `FlutterError.onError` (non-silent) | crash | `flutter_error` | Yes |
| `FlutterError.onError` (silent) | error | `flutter_error` | No |
| `PlatformDispatcher.onError` | crash | `platform_error` | Yes |
| `runZonedGuarded` catch | crash | `zone_uncaught_error` | Yes |
| `ErrorHandlerService.recordCustomError()` | error | `custom_error` | No |

Crashes trigger:
1. `app.crash.count` metric increment
2. `FATAL` log with stack trace
3. `_forceFlushAll()` — parallel flush of traces, metrics, and logs with 3s timeout

---

## 7. Breadcrumb Trail

Last 20 user actions tracked for crash context. Recorded from:

| Breadcrumb Pattern | Source |
|-------------------|--------|
| `navigate:ProductList` | main.dart |
| `navigate:ProductDetail:{productId}` | product_detail_screen.dart |
| `navigate:Cart` | cart_screen.dart |
| `navigate:Checkout` | checkout_screen.dart |
| `navigate:Search` | search_screen.dart |
| `cart:add:{productId}` | cart_service.dart |
| `cart:remove:{productId}` | cart_service.dart |
| `cart:clear` | cart_service.dart |
| `checkout:validate` | checkout_screen.dart |
| `checkout:placeOrder` | checkout_screen.dart |
| `search:{query}` | search_screen.dart |
| `currency:change:{code}` | currency_service.dart |

---

## 8. Battery-Aware Sampling

| Battery State | Sampling Rate | Affected Signals |
|--------------|--------------|-----------------|
| Normal (>= 20%) | 100% | All events, DEBUG/INFO logs |
| Low (10-20%) | 50% | Events sampled, DEBUG/INFO logs sampled |
| Critical (< 10%) | 20% | Events sampled, DEBUG/INFO logs sampled |
| Low Power Mode | 30% | Events sampled, DEBUG/INFO logs sampled |

WARN, ERROR, and FATAL logs are always sent regardless of battery state.
Metrics are always recorded (counters/histograms accumulate and flush on schedule).

---

## 9. Export Configuration

| Signal | Endpoint | Flush Interval | Buffer |
|--------|----------|---------------|--------|
| Traces | `$OTLP_ENDPOINT/$OTLP_TRACES_EXPORTER` | Immediate (individual) + 30s (batch) | 50 events |
| Metrics | `$OTLP_ENDPOINT/$OTLP_METRICS_EXPORTER` | 60s | Unbounded (accumulate until flush) |
| Logs | `$OTLP_ENDPOINT/$OTLP_LOGS_EXPORTER` | 30s | 100 records (auto-flush at capacity) |

All exports include `Authorization: Bearer {token}` when Scout credentials are
configured (`SCOUT_CLIENT_ID`, `SCOUT_CLIENT_SECRET`, `SCOUT_TOKEN_URL`).

---

## 10. Signal Counts

| Category | Count |
|----------|-------|
| Named spans | 10 |
| Event types | ~83 |
| Metrics | 5 |
| Log patterns | 5 |
| Resource attributes | 17 |
| Breadcrumb sources | 12 |
