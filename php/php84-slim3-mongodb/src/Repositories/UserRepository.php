<?php

namespace App\Repositories;

use MongoDB\BSON\ObjectId;
use MongoDB\Collection;
use MongoDB\Database;

class UserRepository
{
    private Collection $collection;

    public function __construct(Database $db)
    {
        $this->collection = $db->selectCollection('users');
    }

    public function findById(string $id): ?array
    {
        $doc = $this->collection->findOne(['_id' => new ObjectId($id)]);
        return $doc ? $this->toArray($doc) : null;
    }

    public function findByEmail(string $email): ?array
    {
        $doc = $this->collection->findOne(['email' => $email]);
        return $doc ? $this->toArray($doc) : null;
    }

    public function create(array $data): array
    {
        $now = new \DateTimeImmutable();
        $document = [
            'name' => $data['name'],
            'email' => $data['email'],
            'password' => password_hash($data['password'], PASSWORD_BCRYPT),
            'created_at' => $now->format('c'),
            'updated_at' => $now->format('c'),
        ];

        $result = $this->collection->insertOne($document);
        $document['_id'] = $result->getInsertedId();

        return $this->toArray($document);
    }

    public function count(): int
    {
        return $this->collection->countDocuments();
    }

    private function toArray($doc): array
    {
        $arr = (array) $doc;
        $arr['id'] = (string) $arr['_id'];
        unset($arr['_id']);
        return $arr;
    }
}
