# syntax=docker/dockerfile:1

ARG PHP_VERSION=8.5

# Stage 1: Build dependencies
FROM php:${PHP_VERSION}-cli AS builder

WORKDIR /app

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
    git \
    unzip \
    libzip-dev && \
    docker-php-ext-install \
    pdo \
    pdo_mysql \
    zip && \
    rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

COPY composer.json ./
RUN composer install --no-dev --no-scripts --no-autoloader --prefer-dist \
    --ignore-platform-reqs

COPY . .
RUN composer dump-autoload --optimize --no-scripts

# Stage 2: Runtime
FROM php:${PHP_VERSION}-cli

WORKDIR /var/www/html

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
    curl \
    libzip-dev \
    default-mysql-client && \
    docker-php-ext-install \
    pdo \
    pdo_mysql \
    zip && \
    pecl install opentelemetry && \
    docker-php-ext-enable opentelemetry && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN groupadd --gid 1000 symfony && \
    useradd --uid 1000 --gid symfony --shell /bin/bash --create-home symfony

COPY --from=builder --chown=symfony:symfony /app /var/www/html

RUN mkdir -p var/cache var/log && \
    chown -R symfony:symfony var

USER symfony

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

CMD ["php", "-S", "0.0.0.0:8080", "-t", "public"]
