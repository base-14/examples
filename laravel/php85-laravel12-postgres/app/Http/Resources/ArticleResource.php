<?php

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class ArticleResource extends JsonResource
{
    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'slug' => $this->slug,
            'title' => $this->title,
            'description' => $this->description,
            'body' => $this->body,
            'tagList' => $this->tags->pluck('name'),
            'createdAt' => $this->created_at->toISOString(),
            'updatedAt' => $this->updated_at->toISOString(),
            'favorited' => $this->isFavoritedBy($request->user()),
            'favoritesCount' => $this->favorites_count,
            'author' => new UserResource($this->author),
        ];
    }
}
