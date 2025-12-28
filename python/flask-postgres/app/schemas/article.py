"""Article-related Marshmallow schemas."""

from marshmallow import Schema, fields, validate

from app.schemas.user import UserSchema


class ArticleSchema(Schema):
    """Schema for article serialization."""

    slug = fields.Str(dump_only=True)
    title = fields.Str(required=True)
    description = fields.Str()
    body = fields.Str(required=True)
    author = fields.Nested(UserSchema, dump_only=True)
    favorites_count = fields.Int(dump_only=True)
    favorited = fields.Bool(dump_only=True)
    created_at = fields.DateTime(dump_only=True, format="iso")
    updated_at = fields.DateTime(dump_only=True, format="iso")


class ArticleCreateSchema(Schema):
    """Schema for article creation validation."""

    title = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    description = fields.Str(validate=validate.Length(max=1000))
    body = fields.Str(required=True, validate=validate.Length(min=1))


class ArticleUpdateSchema(Schema):
    """Schema for article update validation."""

    title = fields.Str(validate=validate.Length(min=1, max=255))
    description = fields.Str(validate=validate.Length(max=1000))
    body = fields.Str(validate=validate.Length(min=1))


class ArticlesResponseSchema(Schema):
    """Schema for paginated articles response."""

    articles = fields.List(fields.Nested(ArticleSchema))
    total = fields.Int()
    page = fields.Int()
    per_page = fields.Int()
