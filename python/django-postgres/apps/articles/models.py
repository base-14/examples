from __future__ import annotations

import re
import time
from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import F


class Article(models.Model):
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    body = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="articles",
    )
    favorites_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "articles"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = self._generate_slug()
        super().save(*args, **kwargs)

    def _generate_slug(self) -> str:
        base_slug = re.sub(r"[^\w\s-]", "", self.title.lower())
        base_slug = re.sub(r"[-\s]+", "-", base_slug).strip("-")
        return f"{base_slug}-{int(time.time() * 1000)}"

    def increment_favorites(self) -> None:
        Article.objects.filter(pk=self.pk).update(favorites_count=F("favorites_count") + 1)
        self.refresh_from_db()

    def decrement_favorites(self) -> None:
        Article.objects.filter(pk=self.pk, favorites_count__gt=0).update(
            favorites_count=F("favorites_count") - 1
        )
        self.refresh_from_db()


class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorites",
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "favorites"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "article"],
                name="unique_user_article_favorite",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user.email} -> {self.article.slug}"
