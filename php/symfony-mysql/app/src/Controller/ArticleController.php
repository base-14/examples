<?php

namespace App\Controller;

use App\Entity\Article;
use App\Repository\ArticleRepository;
use App\Service\NotificationClient;
use OpenTelemetry\API\Metrics\MeterProviderInterface;
use OpenTelemetry\API\Metrics\CounterInterface;
use Psr\Log\LoggerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

#[Route('/api/articles')]
class ArticleController extends AbstractController
{
    private readonly CounterInterface $articlesCreatedCounter;

    public function __construct(
        private readonly ArticleRepository $articleRepository,
        private readonly NotificationClient $notificationClient,
        private readonly LoggerInterface $logger,
        MeterProviderInterface $meterProvider,
    ) {
        $meter = $meterProvider->getMeter('symfony-articles');
        $this->articlesCreatedCounter = $meter->createCounter(
            'articles.created',
            'articles',
            'Number of articles created',
        );
    }

    #[Route('', name: 'article_list', methods: ['GET'])]
    public function list(Request $request): JsonResponse
    {
        $page = max(1, $request->query->getInt('page', 1));
        $perPage = min(100, max(1, $request->query->getInt('per_page', 20)));

        $this->logger->info('Listing articles', ['page' => $page, 'per_page' => $perPage]);

        $result = $this->articleRepository->findPaginated($page, $perPage);
        $data = array_map(fn(Article $a) => $a->toArray(), $result['articles']);

        return new JsonResponse([
            'data' => $data,
            'meta' => [
                'trace_id' => $this->getTraceId(),
                'page' => $page,
                'per_page' => $perPage,
                'total' => $result['total'],
            ],
        ]);
    }

    #[Route('/{id}', name: 'article_show', methods: ['GET'], requirements: ['id' => '\d+'])]
    public function show(int $id): JsonResponse
    {
        $article = $this->articleRepository->find($id);

        if (!$article) {
            $this->logger->warning('Article not found', ['article_id' => $id]);
            return new JsonResponse([
                'error' => ['code' => 'NOT_FOUND', 'message' => 'Article not found'],
                'meta' => ['trace_id' => $this->getTraceId()],
            ], Response::HTTP_NOT_FOUND);
        }

        $this->logger->info('Article retrieved', ['article_id' => $id]);

        return new JsonResponse([
            'data' => $article->toArray(),
            'meta' => ['trace_id' => $this->getTraceId()],
        ]);
    }

    #[Route('', name: 'article_create', methods: ['POST'])]
    public function create(Request $request): JsonResponse
    {
        $payload = json_decode($request->getContent(), true);

        $errors = $this->validate($payload);
        if ($errors) {
            $this->logger->warning('Validation failed', ['errors' => $errors]);
            return new JsonResponse([
                'error' => ['code' => 'VALIDATION_ERROR', 'message' => implode(', ', $errors)],
                'meta' => ['trace_id' => $this->getTraceId()],
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        $article = new Article();
        $article->setTitle($payload['title']);
        $article->setBody($payload['body']);

        $this->articleRepository->save($article);
        $this->articlesCreatedCounter->add(1);
        $this->logger->info('Article created', ['article_id' => $article->getId()]);

        $this->notificationClient->notifyArticleCreated($article->toArray());
        $this->logger->info('Notification sent', ['article_id' => $article->getId()]);

        return new JsonResponse([
            'data' => $article->toArray(),
            'meta' => ['trace_id' => $this->getTraceId()],
        ], Response::HTTP_CREATED);
    }

    #[Route('/{id}', name: 'article_update', methods: ['PUT'], requirements: ['id' => '\d+'])]
    public function update(int $id, Request $request): JsonResponse
    {
        $article = $this->articleRepository->find($id);

        if (!$article) {
            $this->logger->warning('Article not found for update', ['article_id' => $id]);
            return new JsonResponse([
                'error' => ['code' => 'NOT_FOUND', 'message' => 'Article not found'],
                'meta' => ['trace_id' => $this->getTraceId()],
            ], Response::HTTP_NOT_FOUND);
        }

        $payload = json_decode($request->getContent(), true);

        if (!$payload) {
            $this->logger->warning('Validation failed', ['errors' => ['Request body must be valid JSON']]);
            return new JsonResponse([
                'error' => ['code' => 'VALIDATION_ERROR', 'message' => 'Request body must be valid JSON'],
                'meta' => ['trace_id' => $this->getTraceId()],
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        if (isset($payload['title']) && $payload['title'] !== '') {
            if (strlen($payload['title']) > 255) {
                $this->logger->warning('Validation failed', ['errors' => ['title must be 255 characters or less']]);
                return new JsonResponse([
                    'error' => ['code' => 'VALIDATION_ERROR', 'message' => 'title must be 255 characters or less'],
                    'meta' => ['trace_id' => $this->getTraceId()],
                ], Response::HTTP_UNPROCESSABLE_ENTITY);
            }
            $article->setTitle($payload['title']);
        }
        if (isset($payload['body']) && $payload['body'] !== '') {
            $article->setBody($payload['body']);
        }

        $this->articleRepository->save($article);
        $this->logger->info('Article updated', ['article_id' => $id]);

        return new JsonResponse([
            'data' => $article->toArray(),
            'meta' => ['trace_id' => $this->getTraceId()],
        ]);
    }

    #[Route('/{id}', name: 'article_delete', methods: ['DELETE'], requirements: ['id' => '\d+'])]
    public function delete(int $id): JsonResponse
    {
        $article = $this->articleRepository->find($id);

        if (!$article) {
            $this->logger->warning('Article not found for delete', ['article_id' => $id]);
            return new JsonResponse([
                'error' => ['code' => 'NOT_FOUND', 'message' => 'Article not found'],
                'meta' => ['trace_id' => $this->getTraceId()],
            ], Response::HTTP_NOT_FOUND);
        }

        $this->articleRepository->remove($article);
        $this->logger->info('Article deleted', ['article_id' => $id]);

        return new JsonResponse('', Response::HTTP_NO_CONTENT, [], true);
    }

    private function validate(?array $payload): array
    {
        $errors = [];
        if (!$payload) {
            return ['Request body must be valid JSON'];
        }
        if (empty($payload['title'])) {
            $errors[] = 'title is required';
        } elseif (strlen($payload['title']) > 255) {
            $errors[] = 'title must be 255 characters or less';
        }
        if (empty($payload['body'])) {
            $errors[] = 'body is required';
        }
        return $errors;
    }

    private function getTraceId(): string
    {
        $span = \OpenTelemetry\API\Trace\Span::getCurrent();
        $context = $span->getContext();
        return $context->getTraceId();
    }
}
