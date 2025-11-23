# syntax=docker/dockerfile:1

ARG PHP_VERSION=8.1
FROM php:${PHP_VERSION}-cli

# Laravel app lives here
WORKDIR /var/www/html

# Install system dependencies and PHP extensions required by Laravel
RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
    curl \
    git \
    unzip \
    libzip-dev \
    sqlite3 \
    libsqlite3-dev \
    libonig-dev \
    libxml2-dev && \
    docker-php-ext-install \
    pdo \
    pdo_sqlite \
    zip \
    bcmath \
    mbstring \
    xml && \
    rm -rf /var/lib/apt/lists /var/cache/apt/archives

# Install Composer
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

# Install OpenTelemetry PHP extension via PECL
RUN pecl install opentelemetry && \
    docker-php-ext-enable opentelemetry

# Copy composer files and install dependencies
COPY composer.json composer.lock ./
RUN composer install --prefer-dist --no-interaction --no-scripts --no-progress

# Copy application code
COPY . .

# Set proper permissions for Laravel storage and cache
RUN chown -R www-data:www-data /var/www/html/storage /var/www/html/bootstrap/cache && \
    chmod -R 775 /var/www/html/storage /var/www/html/bootstrap/cache

# Create SQLite database file
RUN touch /var/www/html/database/database.sqlite && \
    chown www-data:www-data /var/www/html/database/database.sqlite && \
    chmod 664 /var/www/html/database/database.sqlite

# Run composer post-install scripts
RUN composer dump-autoload --optimize

# Expose port 8000
EXPOSE 8000

# Start Laravel development server
CMD ["php", "artisan", "serve", "--host=0.0.0.0", "--port=8000"]
