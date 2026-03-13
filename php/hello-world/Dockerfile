FROM php:8.3-cli

RUN apt-get update && apt-get install -y unzip && rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

WORKDIR /app
COPY composer.json .
RUN composer install --no-interaction

COPY main.php .

ENTRYPOINT ["php", "main.php"]
