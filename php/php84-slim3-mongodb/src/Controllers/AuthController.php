<?php

namespace App\Controllers;

use App\Telemetry\Metrics;
use Firebase\JWT\JWT;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Log\LoggerInterface;
use Slim\Container;

class AuthController
{
    private Container $container;
    private LoggerInterface $logger;

    public function __construct(Container $container)
    {
        $this->container = $container;
        $this->logger = $container['logger'];
    }

    public function register(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $data = $request->getParsedBody();

        if (empty($data['name']) || empty($data['email']) || empty($data['password'])) {
            $this->logger->warning('Registration validation failed', ['reason' => 'missing fields']);
            return $response->withJson(['error' => 'Name, email and password are required'], 422);
        }

        $repo = $this->container['userRepository'];

        if ($repo->findByEmail($data['email'])) {
            $this->logger->warning('Registration failed: duplicate email', ['email' => $data['email']]);
            return $response->withJson(['error' => 'Email already taken'], 422);
        }

        $user = $repo->create($data);
        $token = $this->generateToken($user);
        Metrics::authRegistration();

        $this->logger->info('User registered', ['user.id' => $user['id']]);

        return $response->withJson([
            'user' => [
                'id' => $user['id'],
                'name' => $user['name'],
                'email' => $user['email'],
                'token' => $token,
            ],
        ], 201);
    }

    public function login(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $data = $request->getParsedBody();

        if (empty($data['email']) || empty($data['password'])) {
            $this->logger->warning('Login validation failed', ['reason' => 'missing fields']);
            Metrics::authLoginFailed();
            return $response->withJson(['error' => 'Email and password are required'], 422);
        }

        $repo = $this->container['userRepository'];
        $user = $repo->findByEmail($data['email']);

        if (!$user || !password_verify($data['password'], $user['password'])) {
            $this->logger->warning('Login failed: invalid credentials', ['email' => $data['email']]);
            Metrics::authLoginFailed();
            return $response->withJson(['error' => 'Invalid credentials'], 401);
        }

        $token = $this->generateToken($user);
        Metrics::authLoginSuccess();

        $this->logger->info('User logged in', ['user.id' => $user['id']]);

        return $response->withJson([
            'user' => [
                'id' => $user['id'],
                'name' => $user['name'],
                'email' => $user['email'],
                'token' => $token,
            ],
        ]);
    }

    public function me(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $userData = $request->getAttribute('user');
        $repo = $this->container['userRepository'];
        $user = $repo->findById($userData['sub']);

        if (!$user) {
            $this->logger->warning('User not found', ['user.id' => $userData['sub']]);
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
            'iat' => $now,
            'exp' => $now + 3600,
        ];

        return JWT::encode($payload, $secret, 'HS256');
    }
}
