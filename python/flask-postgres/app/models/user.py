"""User model."""

import hashlib
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(db.Model):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[str] = mapped_column(String(1000), default="")
    image: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    articles: Mapped[list["Article"]] = relationship(  # noqa: F821
        "Article", back_populates="author", lazy="dynamic"
    )
    favorites: Mapped[list["Favorite"]] = relationship(  # noqa: F821
        "Favorite", back_populates="user", lazy="dynamic"
    )

    def set_password(self, password: str) -> None:
        """Hash and set the user's password.

        Args:
            password: Plain text password to hash.
        """
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify a password against the stored hash.

        Args:
            password: Plain text password to verify.

        Returns:
            True if password matches, False otherwise.
        """
        return check_password_hash(self.password_hash, password)

    @property
    def gravatar_url(self) -> str:
        """Generate Gravatar URL for user's email."""
        email_hash = hashlib.md5(self.email.lower().encode()).hexdigest()
        return f"https://www.gravatar.com/avatar/{email_hash}?d=identicon"

    def __repr__(self) -> str:
        return f"<User {self.email}>"
