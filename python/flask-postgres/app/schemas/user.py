"""User-related Marshmallow schemas."""

from marshmallow import Schema, fields, validate


class UserSchema(Schema):
    """Schema for user serialization."""

    id = fields.Int(dump_only=True)
    email = fields.Email(required=True)
    name = fields.Str(required=True)
    bio = fields.Str()
    image = fields.Str()
    created_at = fields.DateTime(dump_only=True, format="iso")


class RegisterSchema(Schema):
    """Schema for user registration validation."""

    email = fields.Email(required=True)
    password = fields.Str(required=True, load_only=True, validate=validate.Length(min=6))
    name = fields.Str(required=True, validate=validate.Length(min=1, max=255))


class LoginSchema(Schema):
    """Schema for user login validation."""

    email = fields.Email(required=True)
    password = fields.Str(required=True, load_only=True)


class TokenSchema(Schema):
    """Schema for JWT token response."""

    access_token = fields.Str(required=True)
    token_type = fields.Str(dump_default="Bearer")
