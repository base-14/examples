from django.urls import include, path

urlpatterns = [
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.users.urls")),
    path("api/articles/", include("apps.articles.urls")),
]
