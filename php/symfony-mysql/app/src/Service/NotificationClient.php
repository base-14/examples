<?php

namespace App\Service;

use Psr\Log\LoggerInterface;
use Symfony\Contracts\HttpClient\HttpClientInterface;

class NotificationClient
{
    public function __construct(
        private readonly HttpClientInterface $httpClient,
        private readonly LoggerInterface $logger,
        private readonly string $notifyUrl,
    ) {}

    public function notifyArticleCreated(array $articleData): void
    {
        try {
            $response = $this->httpClient->request('POST', $this->notifyUrl . '/notify', [
                'json' => $articleData,
            ]);
            $response->getStatusCode();
        } catch (\Throwable $e) {
            $this->logger->warning('Notification failed', [
                'article_id' => $articleData['id'] ?? null,
                'error' => $e->getMessage(),
            ]);
        }
    }
}
