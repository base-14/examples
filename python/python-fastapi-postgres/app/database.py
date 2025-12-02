from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

from .config import settings

SQLALCHEMY_DATABASE_URL = (f'postgresql://'
                           f'{settings.db_username}:{settings.db_password}'
                           f'@{settings.db_hostname}:{settings.db_port}'
                           f'/{settings.db_name}')

engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Instrument SQLAlchemy for automatic query tracing
SQLAlchemyInstrumentor().instrument(engine=engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
