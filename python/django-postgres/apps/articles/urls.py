from django.urls import path

from . import views

urlpatterns = [
    path("", views.article_list, name="article_list"),
    path("<slug:slug>", views.article_detail, name="article_detail"),
    path("<slug:slug>/favorite", views.favorite_article, name="favorite_article"),
]
