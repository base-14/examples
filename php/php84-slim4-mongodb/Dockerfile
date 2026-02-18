# syntax=docker/dockerfile:1

ARG PHP_VERSION=8.4

# Stage 1: Build dependencies
FROM php:${PHP_VERSION}-cli AS builder

WORKDIR /app

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
    git \
    unzip \
    libzip-dev \
    libssl-dev \
    pkg-config && \
    pecl install mongodb && \
    docker-php-ext-enable mongodb && \
    docker-php-ext-install zip && \
    rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

COPY composer.json ./
RUN composer install --no-dev --no-scripts --no-autoloader --prefer-dist --ignore-platform-req=ext-opentelemetry

COPY . .
RUN composer dump-autoload --optimize --no-scripts

# Stage 2: Runtime
FROM php:${PHP_VERSION}-fpm

WORKDIR /var/www/html

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
    curl \
    libzip-dev \
    libssl-dev \
    libonig-dev \
    libfcgi-bin \
    pkg-config && \
    pecl install mongodb opentelemetry && \
    docker-php-ext-enable mongodb opentelemetry && \
    docker-php-ext-install zip mbstring && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY config/php.ini /usr/local/etc/php/conf.d/99-app.ini
COPY config/php-fpm.conf /usr/local/etc/php-fpm.d/zz-app.conf

RUN groupadd --gid 1000 slim && \
    useradd --uid 1000 --gid slim --shell /bin/bash --create-home slim

COPY --from=builder --chown=slim:slim /app /var/www/html

USER slim

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD SCRIPT_NAME=/ping SCRIPT_FILENAME=/ping REQUEST_METHOD=GET cgi-fcgi -bind -connect 127.0.0.1:9000 | grep -q pong || exit 1

CMD ["php-fpm"]
