<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Http\Resources\TagResource;
use App\Models\Tag;
use Illuminate\Http\JsonResponse;

class TagController extends Controller
{
    public function index(): JsonResponse
    {
        $tags = Tag::all();

        return response()->json([
            'tags' => TagResource::collection($tags),
        ]);
    }
}
