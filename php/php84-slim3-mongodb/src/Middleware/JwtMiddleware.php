<?php

namespace App\Middleware;

use Firebase\JWT\JWT;
use Firebase\JWT\Key;
use OpenTelemetry\API\Trace\Span;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Log\LoggerInterface;

class JwtMiddleware
{
    private LoggerInterface $logger;
    private string $jwtSecret;

    public function __construct(LoggerInterface $logger, string $jwtSecret)
    {
        $this->logger = $logger;
        $this->jwtSecret = $jwtSecret;
    }

    public function __invoke(ServerRequestInterface $request, ResponseInterface $response, callable $next): ResponseInterface
    {
        $authHeader = $request->getHeaderLine('Authorization');

        if (empty($authHeader) || !preg_match('/^Bearer\s+(.+)$/i', $authHeader, $matches)) {
            $this->logger->warning('Authentication failed: missing or malformed token');
            $this->recordAuthFailure('Token required');
            return $response->withJson(['error' => 'Token required'], 401);
        }

        $token = $matches[1];

        try {
            $decoded = JWT::decode($token, new Key($this->jwtSecret, 'HS256'));
            $request = $request->withAttribute('user', (array) $decoded);

            return $next($request, $response);
        } catch (\Exception $e) {
            $this->logger->warning('Authentication failed: invalid token', ['reason' => $e->getMessage()]);
            $this->recordAuthFailure('Invalid token');
            return $response->withJson(['error' => 'Invalid token'], 401);
        }
    }

    private function recordAuthFailure(string $reason): void
    {
        $span = Span::getCurrent();
        $span->setAttribute('app.auth.result', 'failed');
        $span->setAttribute('app.auth.failure_reason', $reason);
    }
}
