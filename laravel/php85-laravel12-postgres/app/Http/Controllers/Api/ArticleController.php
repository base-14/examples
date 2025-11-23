<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Http\Requests\StoreArticleRequest;
use App\Http\Requests\UpdateArticleRequest;
use App\Http\Resources\ArticleResource;
use App\Models\Article;
use App\Models\Tag;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\AnonymousResourceCollection;
use Illuminate\Support\Str;

class ArticleController extends Controller
{
    public function index(Request $request): AnonymousResourceCollection
    {
        $articles = Article::with(['author', 'tags'])
            ->when($request->tag, fn ($q) => $q->whereHas('tags', fn ($q) => $q->where('name', $request->tag)))
            ->when($request->author, fn ($q) => $q->whereHas('author', fn ($q) => $q->where('name', $request->author)))
            ->when($request->favorited, fn ($q) => $q->whereHas('favoritedBy', fn ($q) => $q->where('name', $request->favorited)))
            ->latest()
            ->paginate($request->limit ?? 20);

        return ArticleResource::collection($articles);
    }

    public function store(StoreArticleRequest $request): JsonResponse
    {
        $article = Article::create([
            'author_id' => $request->user()->id,
            'slug' => Str::slug($request->title).'-'.Str::random(6),
            'title' => $request->title,
            'description' => $request->description,
            'body' => $request->body,
        ]);

        if ($request->has('tagList')) {
            $tagIds = collect($request->tagList)->map(function ($tagName) {
                return Tag::firstOrCreate(['name' => $tagName])->id;
            });
            $article->tags()->attach($tagIds);
        }

        $article->load(['author', 'tags']);

        return response()->json([
            'article' => new ArticleResource($article),
        ], 201);
    }

    public function show(Article $article): JsonResponse
    {
        $article->load(['author', 'tags']);

        return response()->json([
            'article' => new ArticleResource($article),
        ]);
    }

    public function update(UpdateArticleRequest $request, Article $article): JsonResponse
    {
        $article->update($request->only(['title', 'description', 'body']));

        if ($request->filled('title')) {
            $article->slug = Str::slug($request->title).'-'.Str::random(6);
            $article->save();
        }

        $article->load(['author', 'tags']);

        return response()->json([
            'article' => new ArticleResource($article),
        ]);
    }

    public function destroy(Request $request, Article $article): JsonResponse
    {
        if ($article->author_id !== $request->user()->id) {
            return response()->json(['error' => 'Forbidden'], 403);
        }

        $article->delete();

        return response()->json(['message' => 'Article deleted successfully']);
    }

    public function feed(Request $request): AnonymousResourceCollection
    {
        $articles = Article::with(['author', 'tags'])
            ->whereHas('author', function ($q) use ($request) {
                $q->whereHas('followers', fn ($q) => $q->where('follower_id', $request->user()->id));
            })
            ->latest()
            ->paginate($request->limit ?? 20);

        return ArticleResource::collection($articles);
    }

    public function favorite(Request $request, Article $article): JsonResponse
    {
        $user = $request->user();

        if (! $article->isFavoritedBy($user)) {
            $article->favoritedBy()->attach($user->id);
        }

        $article->load(['author', 'tags']);

        return response()->json([
            'article' => new ArticleResource($article),
        ]);
    }

    public function unfavorite(Request $request, Article $article): JsonResponse
    {
        $user = $request->user();
        $article->favoritedBy()->detach($user->id);
        $article->load(['author', 'tags']);

        return response()->json([
            'article' => new ArticleResource($article),
        ]);
    }
}
