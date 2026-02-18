<?php

namespace App\Controllers;

use App\Telemetry\Metrics;
use App\Telemetry\TracesOperations;
use Firebase\JWT\JWT;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Slim\Container;

class AuthController
{
    use TracesOperations;

    private Container $container;

    public function __construct(Container $container)
    {
        $this->container = $container;
    }

    public function register(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        return $this->withSpan('auth.register', function ($span) use ($request, $response) {
            $data = $request->getParsedBody();

            if (empty($data['name']) || empty($data['email']) || empty($data['password'])) {
                return $response->withJson(['error' => 'Name, email and password are required'], 422);
            }

            $repo = $this->container['userRepository'];

            if ($repo->findByEmail($data['email'])) {
                return $response->withJson(['error' => 'Email already taken'], 422);
            }

            $user = $repo->create($data);
            $span->setAttribute('user.id', $user['id']);

            $token = $this->generateToken($user);
            Metrics::authRegistration();

            return $response->withJson([
                'user' => [
                    'id' => $user['id'],
                    'name' => $user['name'],
                    'email' => $user['email'],
                    'token' => $token,
                ],
            ], 201);
        }, ['auth.action' => 'register']);
    }

    public function login(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        return $this->withSpan('auth.login', function ($span) use ($request, $response) {
            $data = $request->getParsedBody();

            if (empty($data['email']) || empty($data['password'])) {
                Metrics::authLoginFailed();
                return $response->withJson(['error' => 'Email and password are required'], 422);
            }

            $repo = $this->container['userRepository'];
            $user = $repo->findByEmail($data['email']);

            if (!$user || !password_verify($data['password'], $user['password'])) {
                $span->setAttribute('auth.result', 'failed');
                Metrics::authLoginFailed();
                return $response->withJson(['error' => 'Invalid credentials'], 401);
            }

            $span->setAttribute('user.id', $user['id']);
            $span->setAttribute('auth.result', 'success');

            $token = $this->generateToken($user);
            Metrics::authLoginSuccess();

            return $response->withJson([
                'user' => [
                    'id' => $user['id'],
                    'name' => $user['name'],
                    'email' => $user['email'],
                    'token' => $token,
                ],
            ]);
        }, ['auth.action' => 'login']);
    }

    public function me(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $userData = $request->getAttribute('user');
        $repo = $this->container['userRepository'];
        $user = $repo->findById($userData['sub']);

        if (!$user) {
            return $response->withJson(['error' => 'User not found'], 404);
        }

        return $response->withJson([
            'user' => [
                'id' => $user['id'],
                'name' => $user['name'],
                'email' => $user['email'],
            ],
        ]);
    }

    public function logout(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        Metrics::authLogout();
        return $response->withJson(['message' => 'Logged out successfully']);
    }

    private function generateToken(array $user): string
    {
        $secret = $this->container['jwt_secret'];
        $now = time();
        $payload = [
            'sub' => $user['id'],
            'name' => $user['name'],
            'email' => $user['email'],
            'iat' => $now,
            'exp' => $now + 3600,
        ];

        return JWT::encode($payload, $secret, 'HS256');
    }
}
