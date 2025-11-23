<?php

use App\Http\Controllers\Api\ArticleController;
use App\Http\Controllers\Api\AuthController;
use App\Http\Controllers\Api\CommentController;
use App\Http\Controllers\Api\TagController;
use Illuminate\Support\Facades\Route;

Route::post('/register', [AuthController::class, 'register']);
Route::post('/login', [AuthController::class, 'login']);

Route::get('/tags', [TagController::class, 'index']);
Route::get('/articles', [ArticleController::class, 'index']);
Route::get('/articles/{article}', [ArticleController::class, 'show']);

Route::middleware('jwt.auth')->group(function () {
    Route::post('/logout', [AuthController::class, 'logout']);
    Route::get('/user', [AuthController::class, 'me']);
    Route::post('/refresh', [AuthController::class, 'refresh']);

    Route::get('/articles/feed', [ArticleController::class, 'feed']);
    Route::post('/articles', [ArticleController::class, 'store']);
    Route::put('/articles/{article}', [ArticleController::class, 'update']);
    Route::delete('/articles/{article}', [ArticleController::class, 'destroy']);

    Route::post('/articles/{article}/favorite', [ArticleController::class, 'favorite']);
    Route::delete('/articles/{article}/favorite', [ArticleController::class, 'unfavorite']);

    Route::get('/articles/{article}/comments', [CommentController::class, 'index']);
    Route::post('/articles/{article}/comments', [CommentController::class, 'store']);
    Route::delete('/articles/{article}/comments/{comment}', [CommentController::class, 'destroy']);
});
