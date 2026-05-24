<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Http\Requests\StoreCommentRequest;
use App\Http\Resources\CommentResource;
use App\Models\Article;
use App\Models\Comment;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Resources\Json\AnonymousResourceCollection;

class CommentController extends Controller
{
    public function index(Article $article): AnonymousResourceCollection
    {
        $comments = $article->comments()->with('author')->latest()->get();

        return CommentResource::collection($comments);
    }

    public function store(StoreCommentRequest $request, Article $article): JsonResponse
    {
        $comment = $article->comments()->create([
            'author_id' => $request->user()->id,
            'body' => $request->body,
        ]);

        $comment->load('author');

        return response()->json([
            'comment' => new CommentResource($comment),
        ], 201);
    }

    public function destroy(StoreCommentRequest $request, Article $article, Comment $comment): JsonResponse
    {
        if ($comment->author_id !== $request->user()->id) {
            return response()->json(['error' => 'Forbidden'], 403);
        }

        if ($comment->article_id !== $article->id) {
            return response()->json(['error' => 'Comment does not belong to this article'], 404);
        }

        $comment->delete();

        return response()->json(['message' => 'Comment deleted successfully']);
    }
}
