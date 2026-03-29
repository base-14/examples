# syntax=docker/dockerfile:1

ARG PHP_VERSION=8.5

FROM php:${PHP_VERSION}-cli AS builder

WORKDIR /app

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
    git \
    unzip \
    libzip-dev && \
    docker-php-ext-install zip && \
    rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

COPY composer.json ./
RUN composer install --no-dev --no-scripts --no-autoloader --prefer-dist \
    --ignore-platform-reqs

COPY . .
RUN composer dump-autoload --optimize --no-scripts

FROM php:${PHP_VERSION}-cli

WORKDIR /app

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
    curl \
    libzip-dev && \
    docker-php-ext-install zip && \
    pecl install opentelemetry && \
    docker-php-ext-enable opentelemetry && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN groupadd --gid 1000 notify && \
    useradd --uid 1000 --gid notify --shell /bin/bash --create-home notify

COPY --from=builder --chown=notify:notify /app /app

USER notify

EXPOSE 8081

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8081/health || exit 1

CMD ["php", "-S", "0.0.0.0:8081", "src/index.php"]
