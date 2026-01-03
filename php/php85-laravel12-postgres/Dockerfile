# syntax=docker/dockerfile:1

ARG PHP_VERSION=8.5

# Stage 1: Build dependencies
FROM php:${PHP_VERSION}-cli AS builder

WORKDIR /app

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
    git \
    unzip \
    libzip-dev \
    libpq-dev && \
    docker-php-ext-install \
    pdo \
    pdo_pgsql \
    zip \
    bcmath && \
    rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

COPY composer.json composer.lock ./
RUN composer install --no-dev --no-scripts --no-autoloader --prefer-dist --ignore-platform-req=ext-opentelemetry

COPY . .
RUN composer dump-autoload --optimize --no-scripts

# Stage 2: Runtime
FROM php:${PHP_VERSION}-cli

WORKDIR /var/www/html

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
    curl \
    libzip-dev \
    libpq-dev \
    libonig-dev \
    libxml2-dev \
    postgresql-client && \
    docker-php-ext-install \
    pdo \
    pdo_pgsql \
    zip \
    bcmath \
    mbstring \
    xml && \
    pecl install opentelemetry redis && \
    docker-php-ext-enable opentelemetry redis && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY config/php.ini /usr/local/etc/php/conf.d/99-app.ini

RUN groupadd --gid 1000 laravel && \
    useradd --uid 1000 --gid laravel --shell /bin/bash --create-home laravel

COPY --from=builder --chown=laravel:laravel /app /var/www/html

RUN mkdir -p storage/framework/{sessions,views,cache} storage/logs bootstrap/cache && \
    chown -R laravel:laravel storage bootstrap/cache && \
    chmod -R 775 storage bootstrap/cache

USER laravel

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["php", "artisan", "serve", "--host=0.0.0.0", "--port=8000"]
