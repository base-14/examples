<?php

namespace App\Controllers;

use App\Repositories\ArticleRepository;
use App\Repositories\UserRepository;
use MongoDB\Client;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

class MetricsController
{
    private UserRepository $userRepository;
    private ArticleRepository $articleRepository;
    private Client $mongo;

    public function __construct(UserRepository $userRepository, ArticleRepository $articleRepository, Client $mongo)
    {
        $this->userRepository = $userRepository;
        $this->articleRepository = $articleRepository;
        $this->mongo = $mongo;
    }

    public function metrics(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $userCount = $this->userRepository->count();
        $articleCount = $this->articleRepository->count();

        $dbUp = 0;
        try {
            $this->mongo->selectDatabase('admin')->command(['ping' => 1]);
            $dbUp = 1;
        } catch (\Exception $e) {
            // MongoDB is down
        }

        $metrics = <<<METRICS
# HELP app_users_total Total registered users
# TYPE app_users_total gauge
app_users_total $userCount

# HELP app_articles_total Total articles
# TYPE app_articles_total gauge
app_articles_total $articleCount

# HELP app_database_up Database connection status
# TYPE app_database_up gauge
app_database_up $dbUp

# HELP app_info Application information
# TYPE app_info gauge
app_info{framework="slim",version="4.14",php="8.4",database="mongodb"} 1
METRICS;

        $response->getBody()->write($metrics);
        return $response->withHeader('Content-Type', 'text/plain; charset=utf-8');
    }
}
