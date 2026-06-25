<!-- markdownlint-disable MD041 -->
## Enable OpenTelemetry for PHP 8.4 FPM on Ubuntu

PHP-FPM running on Ubuntu, with an OTel collector on a separate machine in the same network.

### Prerequisites

- PHP 8.4 FPM installed and running
- Composer installed
- OTel collector running on a remote machine (reachable over the network)

### Step 1: Install the PECL OpenTelemetry extension

```bash
sudo pecl install opentelemetry
sudo phpenmod opentelemetry
```

Verify it loaded:

```bash
php -m | grep opentelemetry
```

If `phpenmod` doesn't pick it up, create the ini file manually:

```bash
echo "extension=opentelemetry.so" | sudo tee /etc/php/8.4/mods-available/opentelemetry.ini
sudo phpenmod opentelemetry
```

PHP-FPM may use a different ini path than CLI. Confirm with:

```bash
php-fpm8.4 -m | grep opentelemetry
```

### Step 2: Install Composer packages

In your project directory:

```bash
composer require \
  open-telemetry/sdk \
  open-telemetry/exporter-otlp \
  guzzlehttp/guzzle
```

This pulls the latest compatible versions. Composer's lock file ensures reproducible deploys.

Replace `opentelemetry-auto-slim` with your framework's auto-instrumentation package if applicable (e.g.,
`opentelemetry-auto-laravel`, `opentelemetry-auto-mongodb`).

### Step 3: Configure PHP-FPM pool environment

PHP-FPM strips environment variables by default (`clear_env = yes`). Add the following to the pool config:

```bash
sudo tee -a /etc/php/8.4/fpm/pool.d/www.conf <<'EOF'

; Pass environment to PHP-FPM workers
clear_env = no

; App config
env[MONGO_URI] = mongodb://localhost:27017
env[MONGO_DATABASE] = my_php_fpm_app
env[APP_DEBUG] = true

; OpenTelemetry config
env[OTEL_SERVICE_NAME] = my-php-fpm-app
env[OTEL_EXPORTER_OTLP_ENDPOINT] = http://<COLLECTOR_IP>:4318
env[OTEL_EXPORTER_OTLP_PROTOCOL] = http/protobuf
env[OTEL_TRACES_EXPORTER] = otlp
env[OTEL_METRICS_EXPORTER] = otlp
env[OTEL_LOGS_EXPORTER] = otlp
env[OTEL_PHP_AUTOLOAD_ENABLED] = true
env[OTEL_RESOURCE_ATTRIBUTES] = deployment.environment.name=development,environment=development
EOF
```

Replace `<COLLECTOR_IP>` with the actual IP or hostname of your collector machine.

### Step 4: Restart PHP-FPM

```bash
sudo systemctl restart php8.4-fpm
sudo systemctl status php8.4-fpm
```

### Step 5: Verify collector connectivity

From the PHP-FPM machine:

```bash
# Health check
curl -s http://<COLLECTOR_IP>:13133/

# OTLP endpoint (expect 405 or 200)
curl -s -o /dev/null -w "%{http_code}" http://<COLLECTOR_IP>:4318/v1/traces
```

If these fail, check firewall rules — port 4318 (HTTP) must be open between the two machines.

### Step 6: Verify telemetry is flowing

Hit your app endpoint, then check collector logs on the remote machine for incoming spans.

If nothing shows up, walk through these checks:

1. PHP-FPM error logs: `sudo tail -f /var/log/php8.4-fpm.log`
2. Add a `phpinfo()` route — confirm `opentelemetry` extension appears and `OTEL_*` vars are listed under Environment
3. Confirm Composer autoloader is loaded (`require __DIR__ . '/../vendor/autoload.php'`)

### Troubleshooting

#### OTLP exporter silently drops spans

If auto-discovery of the HTTP client fails, explicitly install the PSR-18 adapter:

```bash
composer require \
  php-http/guzzle7-adapter:^1.1 \
  guzzlehttp/psr7:^2.8
```

#### Notes

- **`clear_env`**: The default is `yes`, which strips all env vars from FPM workers. Setting `clear_env = no` passes
  system-level env vars through. Alternatively, keep it as `yes` and rely on the explicit `env[]` lines.
- **OTLP protocol**: `http/protobuf` uses port 4318. If you switch to `grpc`, use port 4317.
- **`OTEL_PHP_AUTOLOAD_ENABLED`**: This triggers zero-code auto-instrumentation via the Composer packages. Without it,
  you need to manually initialize the SDK in your bootstrap code.
- **Network**: Since the collector is on a different machine, ensure no firewall or security group blocks port 4318
  between the two machines.
