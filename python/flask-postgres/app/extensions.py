"""Flask extensions initialization."""

from flask_marshmallow import Marshmallow
from flask_sqlalchemy import SQLAlchemy


# SQLAlchemy database instance
db = SQLAlchemy()

# Marshmallow serialization instance
ma = Marshmallow()
