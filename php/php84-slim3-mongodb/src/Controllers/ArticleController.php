<?php

namespace App\Controllers;

use App\Telemetry\Metrics;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Log\LoggerInterface;
use Slim\Container;

class ArticleController
{
    private Container $container;
    private LoggerInterface $logger;

    public function __construct(Container $container)
    {
        $this->container = $container;
        $this->logger = $container['logger'];
    }

    public function index(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $params = $request->getQueryParams();
        $limit = (int) ($params['limit'] ?? 20);
        $offset = (int) ($params['offset'] ?? 0);

        $repo = $this->container['articleRepository'];
        $articles = $repo->findAll($limit, $offset);

        return $response->withJson([
            'articles' => $articles,
            'articlesCount' => count($articles),
        ]);
    }

    public function show(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $repo = $this->container['articleRepository'];
        $article = $repo->findById($args['id']);

        if (!$article) {
            $this->logger->warning('Article not found', ['article.id' => $args['id']]);
            return $response->withJson(['error' => 'Article not found'], 404);
        }

        return $response->withJson(['article' => $article]);
    }

    public function create(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $data = $request->getParsedBody();
        $user = $request->getAttribute('user');

        if (empty($data['title']) || empty($data['body'])) {
            $this->logger->warning('Article validation failed', ['reason' => 'missing fields']);
            return $response->withJson(['error' => 'Title and body are required'], 422);
        }

        $data['author_id'] = $user['sub'];

        $repo = $this->container['articleRepository'];
        $article = $repo->create($data);
        Metrics::articleCreated();

        $this->logger->info('Article created', ['article.id' => $article['id'], 'user.id' => $user['sub']]);

        return $response->withJson(['article' => $article], 201);
    }

    public function update(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $user = $request->getAttribute('user');
        $repo = $this->container['articleRepository'];
        $article = $repo->findById($args['id']);

        if (!$article) {
            $this->logger->warning('Article not found', ['article.id' => $args['id']]);
            return $response->withJson(['error' => 'Article not found'], 404);
        }

        if ($article['author_id'] !== $user['sub']) {
            $this->logger->warning('Forbidden: not article owner', ['article.id' => $args['id'], 'user.id' => $user['sub']]);
            return $response->withJson(['error' => 'Forbidden'], 403);
        }

        $data = $request->getParsedBody();
        $updated = $repo->update($args['id'], $data);

        return $response->withJson(['article' => $updated]);
    }

    public function delete(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $user = $request->getAttribute('user');
        $repo = $this->container['articleRepository'];
        $article = $repo->findById($args['id']);

        if (!$article) {
            $this->logger->warning('Article not found', ['article.id' => $args['id']]);
            return $response->withJson(['error' => 'Article not found'], 404);
        }

        if ($article['author_id'] !== $user['sub']) {
            $this->logger->warning('Forbidden: not article owner', ['article.id' => $args['id'], 'user.id' => $user['sub']]);
            return $response->withJson(['error' => 'Forbidden'], 403);
        }

        $repo->delete($args['id']);
        Metrics::articleDeleted();

        $this->logger->info('Article deleted', ['article.id' => $args['id'], 'user.id' => $user['sub']]);

        return $response->withJson(['message' => 'Article deleted']);
    }

    public function favorite(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $user = $request->getAttribute('user');
        $repo = $this->container['articleRepository'];
        $article = $repo->findById($args['id']);

        if (!$article) {
            $this->logger->warning('Article not found', ['article.id' => $args['id']]);
            return $response->withJson(['error' => 'Article not found'], 404);
        }

        $updated = $repo->addFavorite($args['id'], $user['sub']);
        Metrics::articleFavorited();

        return $response->withJson(['article' => $updated]);
    }

    public function unfavorite(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $user = $request->getAttribute('user');
        $repo = $this->container['articleRepository'];
        $article = $repo->findById($args['id']);

        if (!$article) {
            $this->logger->warning('Article not found', ['article.id' => $args['id']]);
            return $response->withJson(['error' => 'Article not found'], 404);
        }

        $updated = $repo->removeFavorite($args['id'], $user['sub']);
        Metrics::articleUnfavorited();

        return $response->withJson(['article' => $updated]);
    }
}
