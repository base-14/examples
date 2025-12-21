<?php

namespace App\Http\Controllers\Api;

use App\Concerns\TracesOperations;
use App\Http\Controllers\Controller;
use App\Http\Requests\StoreArticleRequest;
use App\Http\Requests\UpdateArticleRequest;
use App\Http\Resources\ArticleResource;
use App\Jobs\ProcessArticleJob;
use App\Models\Article;
use App\Models\Tag;
use App\Telemetry\Metrics;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\AnonymousResourceCollection;
use Illuminate\Support\Str;
use OpenTelemetry\API\Trace\StatusCode;

class ArticleController extends Controller
{
    use TracesOperations;

    public function index(Request $request): AnonymousResourceCollection
    {
        return $this->withSpan('article.list', function ($span) use ($request) {
            $span->setAttribute('db.operation', 'read');
            $span->setAttribute('article.filter.tag', $request->tag ?? 'none');
            $span->setAttribute('article.filter.author', $request->author ?? 'none');
            $span->setAttribute('article.limit', $request->limit ?? 20);

            $articles = Article::with(['author', 'tags'])
                ->when($request->tag, fn ($q) => $q->whereHas('tags', fn ($q) => $q->where('name', $request->tag)))
                ->when($request->author, fn ($q) => $q->whereHas('author', fn ($q) => $q->where('name', $request->author)))
                ->when($request->favorited, fn ($q) => $q->whereHas('favoritedBy', fn ($q) => $q->where('name', $request->favorited)))
                ->latest()
                ->paginate($request->limit ?? 20);

            $span->setAttribute('article.count', $articles->count());

            return ArticleResource::collection($articles);
        });
    }

    public function store(StoreArticleRequest $request): JsonResponse
    {
        return $this->withSpan('article.create', function ($span) use ($request) {
            $user = $request->user();
            $span->setAttribute('user.id', $user->id);
            $span->setAttribute('article.title', $request->title);
            $span->setAttribute('db.operation', 'create');
            $span->setAttribute('db.table', 'articles');

            $article = Article::create([
                'author_id' => $user->id,
                'slug' => Str::slug($request->title).'-'.Str::random(6),
                'title' => $request->title,
                'description' => $request->description,
                'body' => $request->body,
            ]);

            $span->setAttribute('article.id', $article->id);
            $span->setAttribute('article.slug', $article->slug);

            if ($request->has('tagList')) {
                $tagIds = collect($request->tagList)->map(function ($tagName) {
                    return Tag::firstOrCreate(['name' => $tagName])->id;
                });
                $article->tags()->attach($tagIds);
                $span->setAttribute('article.tags_count', count($tagIds));
            }

            $article->load(['author', 'tags']);

            ProcessArticleJob::dispatchWithContext($article);
            $span->addEvent('job.dispatched', ['job' => 'ProcessArticleJob']);

            Metrics::articleCreated();

            return response()->json([
                'article' => new ArticleResource($article),
            ], 201);
        });
    }

    public function show(Article $article): JsonResponse
    {
        return $this->withSpan('article.show', function ($span) use ($article) {
            $span->setAttribute('article.id', $article->id);
            $span->setAttribute('article.slug', $article->slug);
            $span->setAttribute('db.operation', 'read');
            $span->setAttribute('db.table', 'articles');

            $article->load(['author', 'tags']);

            $span->setAttribute('article.author_id', $article->author_id);
            $span->setAttribute('article.favorites_count', $article->favorites_count);

            return response()->json([
                'article' => new ArticleResource($article),
            ]);
        });
    }

    public function update(UpdateArticleRequest $request, Article $article): JsonResponse
    {
        return $this->withSpan('article.update', function ($span) use ($request, $article) {
            $user = $request->user();
            $span->setAttribute('user.id', $user->id);
            $span->setAttribute('article.id', $article->id);
            $span->setAttribute('article.slug', $article->slug);
            $span->setAttribute('db.operation', 'update');
            $span->setAttribute('db.table', 'articles');

            $article->update($request->only(['title', 'description', 'body']));

            if ($request->filled('title')) {
                $article->slug = Str::slug($request->title).'-'.Str::random(6);
                $article->save();
                $span->setAttribute('article.new_slug', $article->slug);
            }

            $article->load(['author', 'tags']);

            return response()->json([
                'article' => new ArticleResource($article),
            ]);
        });
    }

    public function destroy(Request $request, Article $article): JsonResponse
    {
        return $this->withSpan('article.delete', function ($span) use ($request, $article) {
            $user = $request->user();
            $span->setAttribute('user.id', $user->id);
            $span->setAttribute('article.id', $article->id);
            $span->setAttribute('article.slug', $article->slug);
            $span->setAttribute('article.author_id', $article->author_id);
            $span->setAttribute('db.operation', 'delete');
            $span->setAttribute('db.table', 'articles');

            if ($article->author_id !== $user->id) {
                $span->setAttribute('error.type', 'authorization');
                $span->setStatus(StatusCode::STATUS_ERROR, 'Forbidden');

                return response()->json(['error' => 'Forbidden'], 403);
            }

            $article->delete();
            $span->addEvent('article.deleted');

            Metrics::articleDeleted();

            return response()->json(['message' => 'Article deleted successfully']);
        });
    }

    public function feed(Request $request): AnonymousResourceCollection
    {
        return $this->withSpan('article.feed', function ($span) use ($request) {
            $user = $request->user();
            $span->setAttribute('user.id', $user->id);
            $span->setAttribute('db.operation', 'read');
            $span->setAttribute('article.limit', $request->limit ?? 20);

            $articles = Article::with(['author', 'tags'])
                ->whereHas('author', function ($q) use ($user) {
                    $q->whereHas('followers', fn ($q) => $q->where('follower_id', $user->id));
                })
                ->latest()
                ->paginate($request->limit ?? 20);

            $span->setAttribute('article.count', $articles->count());

            return ArticleResource::collection($articles);
        });
    }

    public function favorite(Request $request, Article $article): JsonResponse
    {
        return $this->withSpan('article.favorite', function ($span) use ($request, $article) {
            $user = $request->user();
            $span->setAttribute('user.id', $user->id);
            $span->setAttribute('article.id', $article->id);
            $span->setAttribute('article.slug', $article->slug);
            $span->setAttribute('db.operation', 'update');

            $wasAdded = $article->favorite($user);
            $span->setAttribute('article.favorite_added', $wasAdded);

            if ($wasAdded) {
                $span->addEvent('article.favorited');
                Metrics::articleFavorited();
            }

            $article->load(['author', 'tags']);
            $span->setAttribute('article.favorites_count', $article->favorites_count);

            return response()->json([
                'article' => new ArticleResource($article),
            ]);
        });
    }

    public function unfavorite(Request $request, Article $article): JsonResponse
    {
        return $this->withSpan('article.unfavorite', function ($span) use ($request, $article) {
            $user = $request->user();
            $span->setAttribute('user.id', $user->id);
            $span->setAttribute('article.id', $article->id);
            $span->setAttribute('article.slug', $article->slug);
            $span->setAttribute('db.operation', 'update');

            $wasRemoved = $article->unfavorite($user);
            $span->setAttribute('article.favorite_removed', $wasRemoved);

            if ($wasRemoved) {
                $span->addEvent('article.unfavorited');
                Metrics::articleUnfavorited();
            }

            $article->load(['author', 'tags']);
            $span->setAttribute('article.favorites_count', $article->favorites_count);

            return response()->json([
                'article' => new ArticleResource($article),
            ]);
        });
    }
}
