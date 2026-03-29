<?php

namespace App\Repository;

use App\Entity\Article;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;
use Doctrine\ORM\Tools\Pagination\Paginator;
use Doctrine\Persistence\ManagerRegistry;

class ArticleRepository extends ServiceEntityRepository
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, Article::class);
    }

    public function findPaginated(int $page, int $perPage): array
    {
        $query = $this->createQueryBuilder('a')
            ->orderBy('a.createdAt', 'DESC')
            ->setFirstResult(($page - 1) * $perPage)
            ->setMaxResults($perPage)
            ->getQuery();

        $paginator = new Paginator($query);
        $total = count($paginator);

        $articles = [];
        foreach ($paginator as $article) {
            $articles[] = $article;
        }

        return [
            'articles' => $articles,
            'total' => $total,
        ];
    }

    public function save(Article $article): void
    {
        $em = $this->getEntityManager();
        $em->persist($article);
        $em->flush();
    }

    public function remove(Article $article): void
    {
        $em = $this->getEntityManager();
        $em->remove($article);
        $em->flush();
    }
}
