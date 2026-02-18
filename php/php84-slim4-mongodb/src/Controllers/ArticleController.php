<?php

namespace App\Controllers;

use App\Repositories\ArticleRepository;
use App\Telemetry\Metrics;
use App\Telemetry\TracesOperations;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Log\LoggerInterface;

class ArticleController
{
    use TracesOperations;

    private ArticleRepository $articleRepository;
    private LoggerInterface $logger;

    public function __construct(ArticleRepository $articleRepository, LoggerInterface $logger)
    {
        $this->articleRepository = $articleRepository;
        $this->logger = $logger;
    }

    public function index(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        return $this->withSpan('article.list', function ($span) use ($request, $response) {
            $params = $request->getQueryParams();
            $limit = (int) ($params['limit'] ?? 20);
            $offset = (int) ($params['offset'] ?? 0);

            $articles = $this->articleRepository->findAll($limit, $offset);

            $span->setAttribute('app.articles.count', count($articles));

            return $this->json($response, [
                'articles' => $articles,
                'articlesCount' => count($articles),
            ]);
        });
    }

    public function show(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        return $this->withSpan('article.show', function ($span) use ($response, $args) {
            $article = $this->articleRepository->findById($args['id']);

            if (!$article) {
                $this->logger->warning('Article not found', ['article.id' => $args['id']]);
                return $this->json($response, ['error' => 'Article not found'], 404);
            }

            $span->setAttribute('app.article.id', $article['id']);

            return $this->json($response, ['article' => $article]);
        }, ['app.article.id' => $args['id']]);
    }

    public function create(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        return $this->withSpan('article.create', function ($span) use ($request, $response) {
            $data = $request->getParsedBody();
            $user = $request->getAttribute('user');

            if (empty($data['title']) || empty($data['body'])) {
                $this->logger->warning('Article validation failed', ['reason' => 'missing fields']);
                return $this->json($response, ['error' => 'Title and body are required'], 422);
            }

            $data['author_id'] = $user['sub'];

            $article = $this->articleRepository->create($data);

            $span->setAttribute('enduser.id', $user['sub']);
            $span->setAttribute('app.article.id', $article['id']);

            Metrics::articleCreated();

            $this->logger->info('Article created', ['article.id' => $article['id'], 'user.id' => $user['sub']]);

            return $this->json($response, ['article' => $article], 201);
        });
    }

    public function update(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        return $this->withSpan('article.update', function ($span) use ($request, $response, $args) {
            $user = $request->getAttribute('user');
            $article = $this->articleRepository->findById($args['id']);

            if (!$article) {
                $this->logger->warning('Article not found', ['article.id' => $args['id']]);
                return $this->json($response, ['error' => 'Article not found'], 404);
            }

            if ($article['author_id'] !== $user['sub']) {
                $this->logger->warning('Forbidden: not article owner', ['article.id' => $args['id'], 'user.id' => $user['sub']]);
                return $this->json($response, ['error' => 'Forbidden'], 403);
            }

            $data = $request->getParsedBody();
            $updated = $this->articleRepository->update($args['id'], $data);

            $span->setAttribute('enduser.id', $user['sub']);
            $span->setAttribute('app.article.id', $args['id']);

            return $this->json($response, ['article' => $updated]);
        }, ['app.article.id' => $args['id']]);
    }

    public function delete(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        return $this->withSpan('article.delete', function ($span) use ($request, $response, $args) {
            $user = $request->getAttribute('user');
            $article = $this->articleRepository->findById($args['id']);

            if (!$article) {
                $this->logger->warning('Article not found', ['article.id' => $args['id']]);
                return $this->json($response, ['error' => 'Article not found'], 404);
            }

            if ($article['author_id'] !== $user['sub']) {
                $this->logger->warning('Forbidden: not article owner', ['article.id' => $args['id'], 'user.id' => $user['sub']]);
                return $this->json($response, ['error' => 'Forbidden'], 403);
            }

            $this->articleRepository->delete($args['id']);

            $span->setAttribute('enduser.id', $user['sub']);
            $span->setAttribute('app.article.id', $args['id']);

            Metrics::articleDeleted();

            $this->logger->info('Article deleted', ['article.id' => $args['id'], 'user.id' => $user['sub']]);

            return $this->json($response, ['message' => 'Article deleted']);
        }, ['app.article.id' => $args['id']]);
    }

    public function favorite(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        return $this->withSpan('article.favorite', function ($span) use ($request, $response, $args) {
            $user = $request->getAttribute('user');
            $article = $this->articleRepository->findById($args['id']);

            if (!$article) {
                $this->logger->warning('Article not found', ['article.id' => $args['id']]);
                return $this->json($response, ['error' => 'Article not found'], 404);
            }

            $updated = $this->articleRepository->addFavorite($args['id'], $user['sub']);

            $span->setAttribute('enduser.id', $user['sub']);
            $span->setAttribute('app.article.id', $args['id']);

            Metrics::articleFavorited();

            return $this->json($response, ['article' => $updated]);
        }, ['app.article.id' => $args['id']]);
    }

    public function unfavorite(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        return $this->withSpan('article.unfavorite', function ($span) use ($request, $response, $args) {
            $user = $request->getAttribute('user');
            $article = $this->articleRepository->findById($args['id']);

            if (!$article) {
                $this->logger->warning('Article not found', ['article.id' => $args['id']]);
                return $this->json($response, ['error' => 'Article not found'], 404);
            }

            $updated = $this->articleRepository->removeFavorite($args['id'], $user['sub']);

            $span->setAttribute('enduser.id', $user['sub']);
            $span->setAttribute('app.article.id', $args['id']);

            Metrics::articleUnfavorited();

            return $this->json($response, ['article' => $updated]);
        }, ['app.article.id' => $args['id']]);
    }

    private function json(ResponseInterface $response, mixed $data, int $status = 200): ResponseInterface
    {
        $response->getBody()->write(json_encode($data));
        return $response->withHeader('Content-Type', 'application/json')->withStatus($status);
    }
}
