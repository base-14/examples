# Python Examples

OpenTelemetry instrumentation examples for Python applications.

## Projects

| Project | Description |
| ------- | ----------- |
| [django-postgres](./django-postgres) | Django 5.2 LTS + PostgreSQL 18 + Celery with auto-instrumentation, background jobs, and PII masking |
| [flask-postgres](./flask-postgres) | Flask 3.1 + PostgreSQL 18 + Celery with auto-instrumentation, SQLAlchemy, and background jobs |
| [fastapi-postgres](./fastapi-postgres) | Python 3.13 + FastAPI 0.123 with auto-instrumentation, PostgreSQL, and JWT authentication (PyJWT) |
| [fastapi-celery-postgres](./fastapi-celery-postgres) | FastAPI + Celery + PostgreSQL with distributed tracing across async task boundaries |

## Contributing

When adding new examples:

- Include a complete README with setup and usage instructions
- Provide docker-compose setup for easy local testing
- Include OpenTelemetry configuration (collector config recommended)
- Document all environment variables and endpoints
- Add troubleshooting section for common issues
- Keep examples focused and production-ready

Follow the structure of existing projects for consistency.
