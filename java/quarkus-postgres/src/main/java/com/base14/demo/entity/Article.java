package com.base14.demo.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntity;
import io.quarkus.panache.common.Parameters;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import java.time.Instant;
import java.util.List;

@Entity
@Table(name = "articles")
public class Article extends PanacheEntity {

    @Column(unique = true, nullable = false)
    public String slug;

    @Column(nullable = false)
    public String title;

    public String description;

    @Column(columnDefinition = "TEXT")
    public String body;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "author_id", nullable = false)
    public User author;

    @Column(name = "favorites_count", nullable = false)
    public int favoritesCount = 0;

    @Column(name = "created_at", nullable = false, updatable = false)
    public Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    public Instant updatedAt;

    @Transient
    public boolean favorited = false;

    @PrePersist
    public void prePersist() {
        createdAt = Instant.now();
        updatedAt = Instant.now();
    }

    @PreUpdate
    public void preUpdate() {
        updatedAt = Instant.now();
    }

    public static Article findBySlug(String slug) {
        return find("slug", slug).firstResult();
    }

    public static boolean existsBySlug(String slug) {
        return count("slug", slug) > 0;
    }

    public static List<Article> listPaginated(int limit, int offset) {
        return find("ORDER BY createdAt DESC")
                .page(offset / limit, limit)
                .list();
    }

    public static void incrementFavorites(Long id) {
        update("favoritesCount = favoritesCount + 1 WHERE id = ?1", id);
    }

    public static void decrementFavorites(Long id) {
        update("favoritesCount = GREATEST(0, favoritesCount - 1) WHERE id = ?1", id);
    }
}
