<?php

namespace App\Middleware;

use Firebase\JWT\JWT;
use Firebase\JWT\Key;
use OpenTelemetry\API\Trace\Span;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Http\Server\MiddlewareInterface;
use Psr\Http\Server\RequestHandlerInterface;
use Psr\Log\LoggerInterface;
use Slim\Psr7\Response;

class JwtMiddleware implements MiddlewareInterface
{
    private LoggerInterface $logger;
    private string $jwtSecret;

    public function __construct(LoggerInterface $logger, string $jwt_secret)
    {
        $this->logger = $logger;
        $this->jwtSecret = $jwt_secret;
    }

    public function process(ServerRequestInterface $request, RequestHandlerInterface $handler): ResponseInterface
    {
        $authHeader = $request->getHeaderLine('Authorization');

        if (empty($authHeader) || !preg_match('/^Bearer\s+(.+)$/i', $authHeader, $matches)) {
            $this->logger->warning('Authentication failed: missing or malformed token');
            $this->recordAuthFailure('Token required');
            return $this->json(new Response(), ['error' => 'Token required'], 401);
        }

        $token = $matches[1];

        try {
            $decoded = JWT::decode($token, new Key($this->jwtSecret, 'HS256'));
            $request = $request->withAttribute('user', (array) $decoded);

            return $handler->handle($request);
        } catch (\Exception $e) {
            $this->logger->warning('Authentication failed: invalid token', ['reason' => $e->getMessage()]);
            $this->recordAuthFailure('Invalid token');
            return $this->json(new Response(), ['error' => 'Invalid token'], 401);
        }
    }

    private function recordAuthFailure(string $reason): void
    {
        $span = Span::getCurrent();
        $span->setAttribute('app.auth.result', 'failed');
        $span->setAttribute('app.auth.failure_reason', $reason);
    }

    private function json(ResponseInterface $response, mixed $data, int $status = 200): ResponseInterface
    {
        $response->getBody()->write(json_encode($data));
        return $response->withHeader('Content-Type', 'application/json')->withStatus($status);
    }
}
