package com.base14.demo.dto;

import com.base14.demo.entity.Article;
import java.time.Instant;
import java.util.List;

public class ArticleDto {

    public record CreateArticleRequest(String title, String description, String body) {}

    public record UpdateArticleRequest(String title, String description, String body) {}

    public record ArticleResponse(
            Long id,
            String slug,
            String title,
            String description,
            String body,
            AuthorResponse author,
            int favoritesCount,
            boolean favorited,
            Instant createdAt,
            Instant updatedAt
    ) {
        public static ArticleResponse from(Article article) {
            return new ArticleResponse(
                    article.id,
                    article.slug,
                    article.title,
                    article.description,
                    article.body,
                    new AuthorResponse(article.author.id, article.author.name, article.author.bio, article.author.image),
                    article.favoritesCount,
                    article.favorited,
                    article.createdAt,
                    article.updatedAt
            );
        }
    }

    public record AuthorResponse(Long id, String name, String bio, String image) {}

    public record ArticleWrapper(ArticleResponse article) {
        public static ArticleWrapper from(Article article) {
            return new ArticleWrapper(ArticleResponse.from(article));
        }
    }

    public record ArticleListResponse(List<ArticleResponse> articles, int totalCount) {}
}
