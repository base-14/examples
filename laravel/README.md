# Sample Laravel Application

Make sure you have PHP and Composer installed globally on your computer.

Install the app

```bash
composer install
cp .env.example .env
```

Run the web server

```bash
php artisan serve
```

That's it. Now you can use the api, i.e.

```text
http://127.0.0.1:8000/api/articles
```

Visit [docs.base14.io](https://docs.base14.io/instrument/apps/auto-instrumentation/laravel)
for instrumenting laravel applications.
