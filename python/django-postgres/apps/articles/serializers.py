from rest_framework import serializers

from apps.users.serializers import UserSerializer

from .models import Article


class ArticleSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    favorited = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = [
            "slug",
            "title",
            "description",
            "body",
            "author",
            "favorites_count",
            "favorited",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["slug", "author", "favorites_count", "created_at", "updated_at"]

    def get_favorited(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.favorited_by.filter(user=request.user).exists()
        return False


class ArticleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ["title", "description", "body"]


class ArticleUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ["title", "description", "body"]
        extra_kwargs = {
            "title": {"required": False},
            "body": {"required": False},
        }


class ArticleListSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = Article
        fields = [
            "slug",
            "title",
            "description",
            "author",
            "favorites_count",
            "created_at",
        ]
