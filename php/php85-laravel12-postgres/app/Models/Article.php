<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Facades\DB;

class Article extends Model
{
    use HasFactory;

    protected $fillable = [
        'author_id',
        'slug',
        'title',
        'description',
        'body',
        'favorites_count',
    ];

    protected $casts = [
        'favorites_count' => 'integer',
    ];

    public function author(): BelongsTo
    {
        return $this->belongsTo(User::class, 'author_id');
    }

    public function tags(): BelongsToMany
    {
        return $this->belongsToMany(Tag::class);
    }

    public function comments(): HasMany
    {
        return $this->hasMany(Comment::class);
    }

    public function favoritedBy(): BelongsToMany
    {
        return $this->belongsToMany(User::class, 'article_user');
    }

    public function isFavoritedBy(?User $user): bool
    {
        if (! $user) {
            return false;
        }

        return $this->favoritedBy()->where('user_id', $user->id)->exists();
    }

    public function favorite(User $user): bool
    {
        if ($this->isFavoritedBy($user)) {
            return false;
        }

        return DB::transaction(function () use ($user) {
            $this->favoritedBy()->attach($user->id);
            $this->incrementFavoritesCount();
            return true;
        });
    }

    public function unfavorite(User $user): bool
    {
        if (! $this->isFavoritedBy($user)) {
            return false;
        }

        return DB::transaction(function () use ($user) {
            $this->favoritedBy()->detach($user->id);
            $this->decrementFavoritesCount();
            return true;
        });
    }

    public function incrementFavoritesCount(): void
    {
        DB::table('articles')
            ->where('id', $this->id)
            ->increment('favorites_count');

        $this->refresh();
    }

    public function decrementFavoritesCount(): void
    {
        DB::table('articles')
            ->where('id', $this->id)
            ->where('favorites_count', '>', 0)
            ->decrement('favorites_count');

        $this->refresh();
    }
}
