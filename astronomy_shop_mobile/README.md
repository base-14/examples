# 🔭 Astronomy Shop Mobile

A production-ready Flutter e-commerce app with comprehensive OpenTelemetry
observability integration. Built to demonstrate mobile observability patterns
with real-world complexity.

## Features

### E-commerce Core

- Product Catalog - Real astronomy equipment from OpenTelemetry Demo backend
- Shopping Cart - Full cart management with backend synchronization
- Multi-Currency - 6 supported currencies (USD, EUR, CAD, GBP, JPY, INR)
- Checkout Flow - Complete purchase process with order confirmation
- Product Search - Search with intelligent fallbacks

### Observability & Performance

- OpenTelemetry Integration - Complete traces, metrics, and events
- Session Tracking - Unique session correlation across all requests
- HTTP Instrumentation - Every API call traced with rich context
- Business Metrics - Conversion funnel and user journey analytics
- Performance Monitoring - Real-time performance tracking
- Error Boundaries - Comprehensive error handling with telemetry

### Mobile Optimizations

- Battery-Aware Telemetry - Adaptive sampling (100% → 20% on low battery)
- Image Caching - Memory + disk caching with battery optimization
- Intelligent Batching - 50-event batches, 30s flush intervals
- Offline Support - Graceful fallbacks when APIs unavailable

### User Experience

- Material Design 3 - Modern, professional astronomy theme
- Smooth Animations - Hero transitions, loading states, micro-interactions
- Responsive Design - Optimized for mobile and web
- Accessibility - Screen reader support, proper contrast ratios

## Quick Start

### Prerequisites

1. OpenTelemetry Demo running locally:

```bash
git clone https://github.com/open-telemetry/opentelemetry-demo.git
cd opentelemetry-demo
docker compose -f docker-compose.minimal.yml up -d
```

1. Flutter SDK (latest stable version)

1. Chrome browser for web deployment

### Verify Demo Environment

Ensure these services are accessible:

- OpenTelemetry Demo: <http://localhost:8080>
- Jaeger UI: <http://localhost:8080/jaeger/ui/search>
- Demo API: <http://localhost:8080/api>

### Run the App

```bash
cd astronomy_shop_mobile
flutter run -d chrome --web-browser-flag="--disable-web-security" \
  --web-browser-flag="--disable-features=VizDisplayCompositor" \
  --web-hostname localhost --web-port 8090
```

The app will be available at: <http://localhost:8090>

## Observability Demo

### View Traces in Jaeger

1. Open <http://localhost:8080/jaeger/ui/search>
1. Select service: `astronomy-shop-mobile`
1. Explore traces showing:
   - App lifecycle events
   - HTTP API calls with full context
   - User interactions and navigation
   - Business events (cart operations, purchases)

### Key Telemetry Events

- `screen_view` - Navigation tracking
- `product_tap` - Product interactions
- `add_to_cart` - Shopping cart operations
- `checkout_initiated` - Purchase funnel
- `currency_changed` - Internationalization
- `http_request` - All API calls

## Architecture

```plain
lib/
├── main.dart                 # App entry point with providers
├── models/                   # Data models (Product, Cart, Order)
├── screens/                  # UI screens with telemetry integration
├── services/                 # Core services
│   ├── telemetry_service.dart      # OpenTelemetry integration
│   ├── http_service.dart           # API client with tracing
│   ├── cart_service.dart           # Cart state management
│   ├── currency_service.dart       # Multi-currency support
│   └── performance_service.dart    # Performance monitoring
└── widgets/                  # Reusable UI components
```

## Configuration

### Environment Variables

The app uses environment variables for configuration. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Required configuration:

- `API_BASE_URL`: Backend API endpoint (default: `http://localhost:8080/api`)
- `OTLP_ENDPOINT`: Telemetry collector endpoint
- `SERVICE_NAME`: App name for telemetry
- `SERVICE_VERSION`: App version
- `ENVIRONMENT`: development/production

### Telemetry Settings

- Service Name: `astronomy-shop-mobile`
- Sampling Rate: Adaptive (100% → 20% based on battery)
- Batch Size: 50 events
- Flush Interval: 30 seconds

### API Endpoints

- Base URL: Configured in `API_BASE_URL`
- Products: `/products?currencyCode=USD`
- Cart: `/cart`
- Checkout: `/checkout`

## Security & Production Notes

This demo app follows security best practices:

- **No Hardcoded URLs**: All endpoints use environment variables
- **Debug Protection**: Debug logs wrapped in `kDebugMode` checks
- **Clean Code**: Strict linting with `avoid_print` rule
- **Type Safety**: Strict type checking enabled

For production deployment:

- Use HTTPS endpoints in your `.env` file
- Never commit `.env` files with real credentials
- For Base14 Scout: Update `OTLP_ENDPOINT` to your Scout collector endpoint
- Run `flutter analyze` to check code quality
