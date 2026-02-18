<?php

namespace App\Controllers;

use App\Repositories\UserRepository;
use App\Telemetry\Metrics;
use Firebase\JWT\JWT;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Log\LoggerInterface;

class AuthController
{
    private UserRepository $userRepository;
    private LoggerInterface $logger;
    private string $jwtSecret;

    public function __construct(UserRepository $userRepository, LoggerInterface $logger, string $jwt_secret)
    {
        $this->userRepository = $userRepository;
        $this->logger = $logger;
        $this->jwtSecret = $jwt_secret;
    }

    public function register(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $data = $request->getParsedBody();

        if (empty($data['name']) || empty($data['email']) || empty($data['password'])) {
            $this->logger->warning('Registration validation failed', ['reason' => 'missing fields']);
            return $this->json($response, ['error' => 'Name, email and password are required'], 422);
        }

        if ($this->userRepository->findByEmail($data['email'])) {
            $this->logger->warning('Registration failed: duplicate email', ['email' => $data['email']]);
            return $this->json($response, ['error' => 'Email already taken'], 422);
        }

        $user = $this->userRepository->create($data);
        $token = $this->generateToken($user);
        Metrics::authRegistration();

        $this->logger->info('User registered', ['user.id' => $user['id']]);

        return $this->json($response, [
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
            return $this->json($response, ['error' => 'Email and password are required'], 422);
        }

        $user = $this->userRepository->findByEmail($data['email']);

        if (!$user || !password_verify($data['password'], $user['password'])) {
            $this->logger->warning('Login failed: invalid credentials', ['email' => $data['email']]);
            Metrics::authLoginFailed();
            return $this->json($response, ['error' => 'Invalid credentials'], 401);
        }

        $token = $this->generateToken($user);
        Metrics::authLoginSuccess();

        $this->logger->info('User logged in', ['user.id' => $user['id']]);

        return $this->json($response, [
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
        $user = $this->userRepository->findById($userData['sub']);

        if (!$user) {
            $this->logger->warning('User not found', ['user.id' => $userData['sub']]);
            return $this->json($response, ['error' => 'User not found'], 404);
        }

        return $this->json($response, [
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
        return $this->json($response, ['message' => 'Logged out successfully']);
    }

    private function generateToken(array $user): string
    {
        $now = time();
        $payload = [
            'sub' => $user['id'],
            'iat' => $now,
            'exp' => $now + 3600,
        ];

        return JWT::encode($payload, $this->jwtSecret, 'HS256');
    }

    private function json(ResponseInterface $response, mixed $data, int $status = 200): ResponseInterface
    {
        $response->getBody()->write(json_encode($data));
        return $response->withHeader('Content-Type', 'application/json')->withStatus($status);
    }
}
