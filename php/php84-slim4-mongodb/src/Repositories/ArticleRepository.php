<?php

namespace App\Repositories;

use MongoDB\BSON\ObjectId;
use MongoDB\Collection;
use MongoDB\Database;

class ArticleRepository
{
    private Collection $collection;

    public function __construct(Database $db)
    {
        $this->collection = $db->selectCollection('articles');
    }

    public function findAll(int $limit = 20, int $offset = 0): array
    {
        $cursor = $this->collection->find(
            [],
            [
                'sort' => ['created_at' => -1],
                'limit' => $limit,
                'skip' => $offset,
            ]
        );

        $articles = [];
        foreach ($cursor as $doc) {
            $articles[] = $this->toArray($doc);
        }
        return $articles;
    }

    public function findById(string $id): ?array
    {
        try {
            $doc = $this->collection->findOne(['_id' => new ObjectId($id)]);
            return $doc ? $this->toArray($doc) : null;
        } catch (\Exception $e) {
            return null;
        }
    }

    public function create(array $data): array
    {
        $now = new \DateTimeImmutable();
        $document = [
            'slug' => $this->slugify($data['title']),
            'title' => $data['title'],
            'description' => $data['description'] ?? '',
            'body' => $data['body'] ?? '',
            'author_id' => $data['author_id'],
            'tags' => $data['tagList'] ?? [],
            'favorited_by' => [],
            'favorites_count' => 0,
            'created_at' => $now->format('c'),
            'updated_at' => $now->format('c'),
        ];

        $result = $this->collection->insertOne($document);
        $document['_id'] = $result->getInsertedId();

        return $this->toArray($document);
    }

    public function update(string $id, array $data): ?array
    {
        $update = ['updated_at' => (new \DateTimeImmutable())->format('c')];

        if (isset($data['title'])) {
            $update['title'] = $data['title'];
            $update['slug'] = $this->slugify($data['title']);
        }
        if (isset($data['description'])) {
            $update['description'] = $data['description'];
        }
        if (isset($data['body'])) {
            $update['body'] = $data['body'];
        }
        if (isset($data['tagList'])) {
            $update['tags'] = $data['tagList'];
        }

        $this->collection->updateOne(
            ['_id' => new ObjectId($id)],
            ['$set' => $update]
        );

        return $this->findById($id);
    }

    public function delete(string $id): bool
    {
        $result = $this->collection->deleteOne(['_id' => new ObjectId($id)]);
        return $result->getDeletedCount() > 0;
    }

    public function addFavorite(string $articleId, string $userId): ?array
    {
        $this->collection->updateOne(
            ['_id' => new ObjectId($articleId)],
            [
                '$addToSet' => ['favorited_by' => $userId],
                '$inc' => ['favorites_count' => 1],
                '$set' => ['updated_at' => (new \DateTimeImmutable())->format('c')],
            ]
        );

        return $this->findById($articleId);
    }

    public function removeFavorite(string $articleId, string $userId): ?array
    {
        $this->collection->updateOne(
            ['_id' => new ObjectId($articleId)],
            [
                '$pull' => ['favorited_by' => $userId],
                '$inc' => ['favorites_count' => -1],
                '$set' => ['updated_at' => (new \DateTimeImmutable())->format('c')],
            ]
        );

        return $this->findById($articleId);
    }

    public function count(): int
    {
        return $this->collection->countDocuments();
    }

    private function slugify(string $text): string
    {
        $text = strtolower(trim($text));
        $text = preg_replace('/[^a-z0-9]+/', '-', $text);
        $text = trim($text, '-');
        return $text . '-' . substr(uniqid(), -6);
    }

    private function toArray($doc): array
    {
        $arr = (array) $doc;
        $arr['id'] = (string) $arr['_id'];
        unset($arr['_id']);

        if (isset($arr['favorited_by']) && $arr['favorited_by'] instanceof \MongoDB\Model\BSONArray) {
            $arr['favorited_by'] = $arr['favorited_by']->getArrayCopy();
        }
        if (isset($arr['tags']) && $arr['tags'] instanceof \MongoDB\Model\BSONArray) {
            $arr['tags'] = $arr['tags']->getArrayCopy();
        }

        return $arr;
    }
}
