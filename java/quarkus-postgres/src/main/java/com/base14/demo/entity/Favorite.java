package com.base14.demo.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.List;

@Entity
@Table(name = "favorites", uniqueConstraints = {
    @UniqueConstraint(columnNames = {"user_id", "article_id"})
})
public class Favorite extends PanacheEntity {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    public User user;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "article_id", nullable = false)
    public Article article;

    @Column(name = "created_at", nullable = false, updatable = false)
    public Instant createdAt;

    @PrePersist
    public void prePersist() {
        createdAt = Instant.now();
    }

    public static boolean exists(Long userId, Long articleId) {
        return count("user.id = ?1 AND article.id = ?2", userId, articleId) > 0;
    }

    public static Favorite findByUserAndArticle(Long userId, Long articleId) {
        return find("user.id = ?1 AND article.id = ?2", userId, articleId).firstResult();
    }

    public static List<Long> findArticleIdsByUser(Long userId) {
        return find("SELECT f.article.id FROM Favorite f WHERE f.user.id = ?1", userId).project(Long.class).list();
    }

    public static long deleteByUserAndArticle(Long userId, Long articleId) {
        return delete("user.id = ?1 AND article.id = ?2", userId, articleId);
    }
}
