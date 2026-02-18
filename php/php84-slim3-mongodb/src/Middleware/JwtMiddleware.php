<?php

namespace App\Middleware;

use Firebase\JWT\JWT;
use Firebase\JWT\Key;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

class JwtMiddleware
{
    public function __invoke(ServerRequestInterface $request, ResponseInterface $response, callable $next): ResponseInterface
    {
        $authHeader = $request->getHeaderLine('Authorization');

        if (empty($authHeader) || !preg_match('/^Bearer\s+(.+)$/i', $authHeader, $matches)) {
            return $response->withJson(['error' => 'Token required'], 401);
        }

        $token = $matches[1];
        $secret = $_ENV['JWT_SECRET'] ?? 'change-this-secret-in-production-use-a-long-random-string';

        try {
            $decoded = JWT::decode($token, new Key($secret, 'HS256'));
            $request = $request->withAttribute('user', (array) $decoded);

            return $next($request, $response);
        } catch (\Exception $e) {
            return $response->withJson(['error' => 'Invalid token'], 401);
        }
    }
}
