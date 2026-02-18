<?php

namespace App\Controllers;

use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Slim\Container;

class HealthController
{
    private Container $container;

    public function __construct(Container $container)
    {
        $this->container = $container;
    }

    public function health(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $mongoStatus = 'down';
        try {
            $this->container['mongo']->selectDatabase('admin')->command(['ping' => 1]);
            $mongoStatus = 'up';
        } catch (\Exception $e) {
            // MongoDB is down
        }

        $status = $mongoStatus === 'up' ? 'healthy' : 'unhealthy';

        $data = [
            'status' => $status,
            'components' => [
                'mongodb' => $mongoStatus,
            ],
            'timestamp' => (new \DateTimeImmutable())->format('c'),
        ];

        $statusCode = $status === 'healthy' ? 200 : 503;
        return $response->withJson($data, $statusCode);
    }
}
