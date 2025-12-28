from django.urls import path

from . import views

urlpatterns = [
    path("register", views.register, name="register"),
    path("login", views.login, name="login"),
    path("user", views.get_user, name="get_user"),
    path("logout", views.logout, name="logout"),
]
