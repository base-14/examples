<?php

namespace App\Controllers;

use MongoDB\Client;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Log\LoggerInterface;

class HealthController
{
    private Client $mongo;
    private LoggerInterface $logger;

    public function __construct(Client $mongo, LoggerInterface $logger)
    {
        $this->mongo = $mongo;
        $this->logger = $logger;
    }

    public function health(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $mongoStatus = 'down';
        try {
            $this->mongo->selectDatabase('admin')->command(['ping' => 1]);
            $mongoStatus = 'up';
        } catch (\Exception $e) {
            $this->logger->warning('MongoDB health check failed', ['exception' => $e->getMessage()]);
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
        return $this->json($response, $data, $statusCode);
    }

    private function json(ResponseInterface $response, mixed $data, int $status = 200): ResponseInterface
    {
        $response->getBody()->write(json_encode($data));
        return $response->withHeader('Content-Type', 'application/json')->withStatus($status);
    }
}
