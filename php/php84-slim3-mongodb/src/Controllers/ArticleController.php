<?php

namespace App\Controllers;

use App\Telemetry\Metrics;
use App\Telemetry\TracesOperations;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Slim\Container;

class ArticleController
{
    use TracesOperations;

    private Container $container;

    public function __construct(Container $container)
    {
        $this->container = $container;
    }

    public function index(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        return $this->withSpan('article.list', function ($span) use ($request, $response) {
            $params = $request->getQueryParams();
            $limit = (int) ($params['limit'] ?? 20);
            $offset = (int) ($params['offset'] ?? 0);

            $repo = $this->container['articleRepository'];
            $articles = $repo->findAll($limit, $offset);

            $span->setAttribute('db.operation', 'find');
            $span->setAttribute('articles.count', count($articles));

            return $response->withJson([
                'articles' => $articles,
                'articlesCount' => count($articles),
            ]);
        });
    }

    public function show(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        return $this->withSpan('article.show', function ($span) use ($response, $args) {
            $repo = $this->container['articleRepository'];
            $article = $repo->findById($args['id']);

            if (!$article) {
                return $response->withJson(['error' => 'Article not found'], 404);
            }

            $span->setAttribute('article.id', $article['id']);
            $span->setAttribute('db.operation', 'findOne');

            return $response->withJson(['article' => $article]);
        }, ['article.id' => $args['id']]);
    }

    public function create(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        return $this->withSpan('article.create', function ($span) use ($request, $response) {
            $data = $request->getParsedBody();
            $user = $request->getAttribute('user');

            if (empty($data['title']) || empty($data['body'])) {
                return $response->withJson(['error' => 'Title and body are required'], 422);
            }

            $data['author_id'] = $user['sub'];

            $repo = $this->container['articleRepository'];
            $article = $repo->create($data);

            $span->setAttribute('user.id', $user['sub']);
            $span->setAttribute('article.id', $article['id']);
            $span->setAttribute('db.operation', 'insertOne');

            Metrics::articleCreated();

            return $response->withJson(['article' => $article], 201);
        }, ['db.operation' => 'insertOne']);
    }

    public function update(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        return $this->withSpan('article.update', function ($span) use ($request, $response, $args) {
            $user = $request->getAttribute('user');
            $repo = $this->container['articleRepository'];
            $article = $repo->findById($args['id']);

            if (!$article) {
                return $response->withJson(['error' => 'Article not found'], 404);
            }

            if ($article['author_id'] !== $user['sub']) {
                return $response->withJson(['error' => 'Forbidden'], 403);
            }

            $data = $request->getParsedBody();
            $updated = $repo->update($args['id'], $data);

            $span->setAttribute('user.id', $user['sub']);
            $span->setAttribute('article.id', $args['id']);
            $span->setAttribute('db.operation', 'updateOne');

            return $response->withJson(['article' => $updated]);
        }, ['article.id' => $args['id']]);
    }

    public function delete(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        return $this->withSpan('article.delete', function ($span) use ($request, $response, $args) {
            $user = $request->getAttribute('user');
            $repo = $this->container['articleRepository'];
            $article = $repo->findById($args['id']);

            if (!$article) {
                return $response->withJson(['error' => 'Article not found'], 404);
            }

            if ($article['author_id'] !== $user['sub']) {
                return $response->withJson(['error' => 'Forbidden'], 403);
            }

            $repo->delete($args['id']);

            $span->setAttribute('user.id', $user['sub']);
            $span->setAttribute('article.id', $args['id']);
            $span->setAttribute('db.operation', 'deleteOne');

            Metrics::articleDeleted();

            return $response->withJson(['message' => 'Article deleted']);
        }, ['article.id' => $args['id']]);
    }

    public function favorite(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        return $this->withSpan('article.favorite', function ($span) use ($request, $response, $args) {
            $user = $request->getAttribute('user');
            $repo = $this->container['articleRepository'];
            $article = $repo->findById($args['id']);

            if (!$article) {
                return $response->withJson(['error' => 'Article not found'], 404);
            }

            $updated = $repo->addFavorite($args['id'], $user['sub']);

            $span->setAttribute('user.id', $user['sub']);
            $span->setAttribute('article.id', $args['id']);
            $span->setAttribute('db.operation', 'updateOne');

            Metrics::articleFavorited();

            return $response->withJson(['article' => $updated]);
        }, ['article.id' => $args['id']]);
    }

    public function unfavorite(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        return $this->withSpan('article.unfavorite', function ($span) use ($request, $response, $args) {
            $user = $request->getAttribute('user');
            $repo = $this->container['articleRepository'];
            $article = $repo->findById($args['id']);

            if (!$article) {
                return $response->withJson(['error' => 'Article not found'], 404);
            }

            $updated = $repo->removeFavorite($args['id'], $user['sub']);

            $span->setAttribute('user.id', $user['sub']);
            $span->setAttribute('article.id', $args['id']);
            $span->setAttribute('db.operation', 'updateOne');

            Metrics::articleUnfavorited();

            return $response->withJson(['article' => $updated]);
        }, ['article.id' => $args['id']]);
    }
}
