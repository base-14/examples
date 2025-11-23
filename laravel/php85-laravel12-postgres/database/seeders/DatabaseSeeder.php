<?php

namespace Database\Seeders;

use App\Models\Article;
use App\Models\Comment;
use App\Models\Tag;
use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Str;

class DatabaseSeeder extends Seeder
{
    /**
     * Seed the application's database.
     */
    public function run(): void
    {
        // Create users
        $alice = User::create([
            'name' => 'Alice Smith',
            'email' => 'alice@example.com',
            'password' => Hash::make('password'),
            'bio' => 'Full-stack developer passionate about Laravel and OpenTelemetry',
            'image' => 'https://api.dicebear.com/7.x/avataaars/svg?seed=Alice',
        ]);

        $bob = User::create([
            'name' => 'Bob Johnson',
            'email' => 'bob@example.com',
            'password' => Hash::make('password'),
            'bio' => 'DevOps engineer specializing in observability',
            'image' => 'https://api.dicebear.com/7.x/avataaars/svg?seed=Bob',
        ]);

        $charlie = User::create([
            'name' => 'Charlie Davis',
            'email' => 'charlie@example.com',
            'password' => Hash::make('password'),
            'bio' => 'Database administrator and PostgreSQL expert',
            'image' => 'https://api.dicebear.com/7.x/avataaars/svg?seed=Charlie',
        ]);

        // Create tags
        $tags = [
            Tag::create(['name' => 'laravel']),
            Tag::create(['name' => 'php']),
            Tag::create(['name' => 'opentelemetry']),
            Tag::create(['name' => 'postgresql']),
            Tag::create(['name' => 'docker']),
            Tag::create(['name' => 'observability']),
            Tag::create(['name' => 'distributed-tracing']),
        ];

        // Create articles
        $article1 = Article::create([
            'author_id' => $alice->id,
            'slug' => 'getting-started-laravel-12-'.Str::random(6),
            'title' => 'Getting Started with Laravel 12',
            'description' => 'A comprehensive guide to Laravel 12 new features',
            'body' => 'Laravel 12 introduces several exciting features including improved performance, better developer experience, and enhanced security. This article explores the key changes and how to leverage them in your applications.',
        ]);
        $article1->tags()->attach([$tags[0]->id, $tags[1]->id]);

        $article2 = Article::create([
            'author_id' => $alice->id,
            'slug' => 'opentelemetry-php-instrumentation-'.Str::random(6),
            'title' => 'OpenTelemetry Auto-Instrumentation in PHP',
            'description' => 'Implementing automatic tracing without code changes',
            'body' => 'OpenTelemetry provides automatic instrumentation for PHP applications through the opentelemetry-auto-laravel package. This eliminates the need for manual span creation and makes observability seamless. Learn how to set up automatic tracing in your Laravel applications.',
        ]);
        $article2->tags()->attach([$tags[0]->id, $tags[2]->id, $tags[5]->id, $tags[6]->id]);

        $article3 = Article::create([
            'author_id' => $bob->id,
            'slug' => 'docker-compose-laravel-'.Str::random(6),
            'title' => 'Docker Compose Setup for Laravel',
            'description' => 'Complete Docker setup with PostgreSQL and OpenTelemetry',
            'body' => 'Learn how to set up a production-ready Laravel development environment using Docker Compose. This guide covers multi-container orchestration with PostgreSQL, Redis, and OpenTelemetry Collector for comprehensive observability.',
        ]);
        $article3->tags()->attach([$tags[0]->id, $tags[4]->id]);

        $article4 = Article::create([
            'author_id' => $charlie->id,
            'slug' => 'postgresql-18-features-'.Str::random(6),
            'title' => 'PostgreSQL 18 Performance Tips',
            'description' => 'Optimizing queries and indexing strategies',
            'body' => 'PostgreSQL 18 brings significant performance improvements and new features. This article covers query optimization techniques, proper indexing strategies, and how to monitor database performance using OpenTelemetry instrumentation.',
        ]);
        $article4->tags()->attach([$tags[3]->id, $tags[5]->id]);

        $article5 = Article::create([
            'author_id' => $bob->id,
            'slug' => 'distributed-tracing-microservices-'.Str::random(6),
            'title' => 'Distributed Tracing in Microservices',
            'description' => 'Understanding trace context propagation',
            'body' => 'Distributed tracing is essential for debugging microservices architectures. Learn how OpenTelemetry propagates trace context across service boundaries and how to visualize end-to-end request flows in your observability platform.',
        ]);
        $article5->tags()->attach([$tags[2]->id, $tags[5]->id, $tags[6]->id]);

        // Create comments
        Comment::create([
            'article_id' => $article1->id,
            'author_id' => $bob->id,
            'body' => 'Great introduction to Laravel 12! The section on improved performance is particularly interesting.',
        ]);

        Comment::create([
            'article_id' => $article1->id,
            'author_id' => $charlie->id,
            'body' => 'Thanks for this guide. The code examples are very helpful for understanding the new features.',
        ]);

        Comment::create([
            'article_id' => $article2->id,
            'author_id' => $bob->id,
            'body' => 'Auto-instrumentation is a game changer! No more manual span creation everywhere.',
        ]);

        Comment::create([
            'article_id' => $article3->id,
            'author_id' => $alice->id,
            'body' => 'Excellent Docker setup guide. I used this for my team\'s development environment.',
        ]);

        Comment::create([
            'article_id' => $article4->id,
            'author_id' => $alice->id,
            'body' => 'The indexing strategies section helped me optimize our slow queries. Performance improved by 10x!',
        ]);

        // Create favorites (without timestamps)
        $article1->favoritedBy()->syncWithoutDetaching([$bob->id, $charlie->id]);
        $article2->favoritedBy()->syncWithoutDetaching([$bob->id]);
        $article3->favoritedBy()->syncWithoutDetaching([$alice->id]);
        $article4->favoritedBy()->syncWithoutDetaching([$alice->id, $bob->id]);

        // Create follower relationships (without timestamps)
        $alice->followers()->syncWithoutDetaching([$bob->id, $charlie->id]);
        $bob->followers()->syncWithoutDetaching([$alice->id]);

        $this->command->info('Database seeded successfully!');
        $this->command->info('Users: alice@example.com, bob@example.com, charlie@example.com');
        $this->command->info('Password: password');
    }
}
