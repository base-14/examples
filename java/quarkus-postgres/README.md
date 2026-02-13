# Quarkus + PostgreSQL + OpenTelemetry

Production-ready Quarkus REST API with built-in OpenTelemetry instrumentation, JWT authentication, and PostgreSQL integration with base14 Scout.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/java)

## Stack Profile

| Component | Version | EOL Status | Current Version |
|-----------|---------|------------|-----------------|
| **Java** | 21 | Sep 2028 | LTS release |
| **Quarkus** | 3.31 | Active | 3.31.3 |
| **PostgreSQL** | 18 | Nov 2029 | 18.1 |
| **Hibernate** | 6.6 | Active | Bundled with Quarkus |
| **OpenTelemetry** | Built-in | N/A | Quarkus extension |
| **Maven** | 3.9+ | Active | Build tool |

**Why This Stack**: Demonstrates Quarkus with native OpenTelemetry support, supersonic startup times,
low memory footprint, and comprehensive observability for cloud-native Java applications.

## Architecture Notes

### Synchronous REST API Pattern

This example focuses on demonstrating **synchronous REST API** instrumentation with Quarkus.
Unlike other examples in this repository (Express5, NestJS, Django, Flask, Go Echo, Go Fiber)
which include background job processing, this example intentionally omits asynchronous job queues.

**Why No Background Jobs?**

1. **Focus on Native Compilation**: Quarkus excels at native image compilation, and this example
   demonstrates OTEL instrumentation that works seamlessly in both JVM and native modes
2. **Unique Value Proposition**: While other examples demonstrate async patterns (BullMQ, Celery, Asynq, River),
   Quarkus showcases reactive programming, native compilation, and built-in OTEL support
3. **Educational Clarity**: Simplifies the example to focus on Quarkus-specific features without the complexity of job queue integration

**For Async Job Patterns**: See other examples in this repository:

- **Node.js**: Express5 or NestJS (BullMQ with Redis)
- **Python**: Django or Flask (Celery with Redis)
- **Go**: Echo (Asynq with Redis) or Fiber (River with PostgreSQL)

## What's Instrumented

### Automatic Instrumentation

- ✅ HTTP requests and responses (RESTEasy Reactive)
- ✅ Database queries (Hibernate ORM/JDBC)
- ✅ JVM metrics (memory, GC, threads, CPU)
- ✅ Distributed trace propagation (W3C Trace Context)
- ✅ Exception tracking with stack traces

### Custom Instrumentation

- **Traces**: Business spans using `@WithSpan` annotation
- **Attributes**: User ID, article slug, operation metadata
- **Metrics**: Article operations, favorites, authentication attempts
- **Logs**: Trace-correlated logging with traceId/spanId

### Quarkus OpenTelemetry Extension

Uses `quarkus-opentelemetry` extension for zero-configuration instrumentation:

```xml
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-opentelemetry</artifactId>
</dependency>
```

Benefits:

- Native compilation support
- Automatic context propagation
- Low overhead instrumentation
- Integration with Quarkus ecosystem

## Prerequisites

1. **Docker & Docker Compose** - [Install Docker](https://docs.docker.com/get-docker/)
2. **base14 Scout Account** - [Sign up](https://base14.io)
3. **Java 21+ and Maven 3.9+** (for local development)

## Quick Start

### 1. Generate JWT Keys (First Time Only)

⚠️ The example includes demo keys. For production or your own testing, generate new ones:

```bash
# Generate new RSA key pair for JWT signing
openssl genrsa -out src/main/resources/privateKey.pem 2048
openssl rsa -in src/main/resources/privateKey.pem -pubout -out src/main/resources/publicKey.pem

# Never commit privateKey.pem (already in .gitignore)
```

### 2. Clone and Navigate

```bash
git clone https://github.com/base-14/examples.git
cd examples/java/quarkus-postgres
```

### 3. Set base14 Scout Credentials

```bash
export SCOUT_ENDPOINT=https://your-tenant.base14.io:4318
export SCOUT_CLIENT_ID=your_client_id
export SCOUT_CLIENT_SECRET=your_client_secret
export SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
```

### 4. Start Services

```bash
docker compose up --build -d
```

This starts:

- Quarkus application on port 8080
- PostgreSQL on port 5432
- OpenTelemetry Collector on ports 4317/4318

### 5. Verify Health

```bash
# Check application health
curl http://localhost:8080/api/health

# Check Quarkus SmallRye health
curl http://localhost:8080/q/health
```

### 6. Run API Tests

```bash
./scripts/test-api.sh
```

This script exercises all API endpoints and generates telemetry data.

## API Endpoints

### Health

| Method | Endpoint      | Description             | Auth |
| ------ | ------------- | ----------------------- | ---- |
| `GET`  | `/api/health` | Custom health check     | No   |
| `GET`  | `/q/health`   | Quarkus SmallRye health | No   |

### Authentication

| Method | Endpoint        | Description               | Auth |
| ------ | --------------- | ------------------------- | ---- |
| `POST` | `/api/register` | Register new user         | No   |
| `POST` | `/api/login`    | Login and get JWT token   | No   |
| `GET`  | `/api/user`     | Get current user profile  | Yes  |
| `POST` | `/api/logout`   | Logout                    | Yes  |

### Articles

| Method   | Endpoint                     | Description                  | Auth        |
| -------- | ---------------------------- | ---------------------------- | ----------- |
| `GET`    | `/api/articles`              | List articles (paginated)    | No          |
| `POST`   | `/api/articles`              | Create article               | Yes         |
| `GET`    | `/api/articles/{slug}`       | Get single article           | No          |
| `PUT`    | `/api/articles/{slug}`       | Update article               | Yes (owner) |
| `DELETE` | `/api/articles/{slug}`       | Delete article               | Yes (owner) |
| `POST`   | `/api/articles/{slug}/favorite`   | Favorite article        | Yes         |
| `DELETE` | `/api/articles/{slug}/favorite`   | Unfavorite article      | Yes         |

## API Examples

### Register User

```bash
curl -X POST http://localhost:8080/api/register \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "name": "Alice", "password": "password123"}'
```

Response:

```json
{
  "user": {
    "id": 1,
    "email": "alice@example.com",
    "name": "Alice",
    "bio": null,
    "image": null
  },
  "token": "eyJhbGciOiJSUzI1NiIs..."
}
```

### Create Article

```bash
curl -X POST http://localhost:8080/api/articles \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"title": "My Article", "body": "Article content here", "description": "A brief description"}'
```

Response:

```json
{
  "slug": "my-article",
  "title": "My Article",
  "description": "A brief description",
  "body": "Article content here",
  "author": {"id": 1, "email": "alice@example.com", "name": "Alice"},
  "favoritesCount": 0,
  "favorited": false,
  "createdAt": "2025-12-27T06:42:14Z"
}
```

## Error Response Format

All errors return a consistent format:

```json
{
  "error": "Article not found",
  "statusCode": 404,
  "traceId": "abc123..."
}
```

Error responses include trace IDs for correlation with telemetry data.

## Configuration

### Required Environment Variables

| Variable              | Description                | Required |
| --------------------- | -------------------------- | -------- |
| `SCOUT_ENDPOINT`      | base14 Scout OTLP endpoint | Yes      |
| `SCOUT_CLIENT_ID`     | Scout OAuth2 client ID     | Yes      |
| `SCOUT_CLIENT_SECRET` | Scout OAuth2 client secret | Yes      |
| `SCOUT_TOKEN_URL`     | Scout OAuth2 token URL     | Yes      |

### Application Environment Variables

| Variable             | Description            | Default                 |
| -------------------- | ---------------------- | ----------------------- |
| `ENVIRONMENT`        | Deployment environment | `development`           |
| `DB_HOST`            | PostgreSQL host        | `localhost`             |
| `DB_PORT`            | PostgreSQL port        | `5432`                  |
| `DB_NAME`            | Database name          | `quarkus_app`           |
| `DB_USER`            | Database user          | `postgres`              |
| `DB_PASSWORD`        | Database password      | `postgres`              |
| `OTEL_EXPORTER_*`    | OTLP collector         | `http://localhost:4318` |

### Quarkus OpenTelemetry Configuration

Configuration is in `src/main/resources/application.properties`:

```properties
# OpenTelemetry
quarkus.otel.service.name=quarkus-postgres-api
quarkus.otel.traces.enabled=true
quarkus.otel.metrics.enabled=true
quarkus.otel.logs.enabled=true
quarkus.otel.exporter.otlp.endpoint=${OTEL_EXPORTER_OTLP_ENDPOINT:http://localhost:4318}
quarkus.otel.exporter.otlp.protocol=http/protobuf
quarkus.otel.resource.attributes=deployment.environment=${ENVIRONMENT:development}
```

## Telemetry Data

### Traces

Distributed traces capture the full request lifecycle:

- ✅ HTTP request handling with route attributes
- ✅ Database queries with SQL statements
- ✅ Custom business spans using `@WithSpan`
- ✅ Exception tracking with stack traces

**Custom Spans Example**:

```java
@WithSpan("article.create")
public Article createArticle(CreateArticleDto dto, User author) {
    Span span = Span.current();
    span.setAttribute("user.id", author.id);
    span.setAttribute("article.title", dto.title);
    // ... business logic
    return article;
}
```

### Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `http.server.requests` | Counter | HTTP requests by method, route, status |
| `http.server.duration` | Histogram | Request latency |
| `jvm.memory.used` | Gauge | JVM memory usage |
| `jvm.gc.duration` | Histogram | GC pause time |
| `articles.created` | Counter | Articles created |
| `articles.deleted` | Counter | Articles deleted |
| `favorites.added` | Counter | Favorites added |

### Logs

All logs include `traceId` and `spanId` for correlation:

```text
2025-12-27 10:30:45 INFO  traceId=59e443df, spanId=867d079f [c.b.d.r.ArticleResource] (executor-1) Article created: my-article
```

## Database Schema

### Users Table

| Column        | Type         | Description         |
| ------------- | ------------ | ------------------- |
| id            | BIGSERIAL    | Primary key         |
| email         | VARCHAR(255) | Unique email        |
| password_hash | VARCHAR(255) | Hashed password     |
| name          | VARCHAR(255) | Display name        |
| bio           | TEXT         | User bio            |
| image         | VARCHAR(500) | Avatar URL          |
| created_at    | TIMESTAMP    | Creation time       |
| updated_at    | TIMESTAMP    | Last update         |

### Articles Table

| Column          | Type         | Description         |
| --------------- | ------------ | ------------------- |
| id              | BIGSERIAL    | Primary key         |
| slug            | VARCHAR(255) | Unique URL slug     |
| title           | VARCHAR(255) | Article title       |
| description     | TEXT         | Brief description   |
| body            | TEXT         | Article content     |
| author_id       | BIGINT       | FK to users         |
| favorites_count | INTEGER      | Cached favorite cnt |
| created_at      | TIMESTAMP    | Creation time       |
| updated_at      | TIMESTAMP    | Last update         |

### Favorites Table

| Column     | Type      | Description         |
| ---------- | --------- | ------------------- |
| id         | BIGSERIAL | Primary key         |
| user_id    | BIGINT    | FK to users         |
| article_id | BIGINT    | FK to articles      |
| created_at | TIMESTAMP | Creation time       |

## Project Structure

```text
quarkus-postgres/
├── config/
│   └── otel-config.yaml          # OTel Collector config
├── src/
│   ├── main/
│   │   ├── java/com/base14/demo/
│   │   │   ├── dto/              # Data Transfer Objects
│   │   │   │   ├── ArticleDto.java
│   │   │   │   └── AuthDto.java
│   │   │   ├── entity/           # JPA Entities
│   │   │   │   ├── User.java
│   │   │   │   ├── Article.java
│   │   │   │   └── Favorite.java
│   │   │   ├── resource/         # JAX-RS Resources (Controllers)
│   │   │   │   ├── HealthResource.java
│   │   │   │   ├── AuthResource.java
│   │   │   │   └── ArticleResource.java
│   │   │   └── service/          # Business Logic
│   │   │       ├── TelemetryService.java
│   │   │       ├── AuthService.java
│   │   │       ├── ArticleService.java
│   │   │       └── ServiceException.java
│   │   └── resources/
│   │       ├── application.properties  # Quarkus config
│   │       ├── privateKey.pem          # JWT private key (gitignored)
│   │       └── publicKey.pem           # JWT public key
│   └── test/
│       └── java/                 # Tests
├── scripts/
│   └── test-api.sh               # API test script
├── compose.yml                   # Docker Compose
├── Dockerfile                    # Multi-stage build
├── Makefile                      # Build automation
└── pom.xml                       # Maven configuration
```

## Development

### Run Locally (without Docker)

```bash
# Start PostgreSQL
docker compose up postgres -d

# Run in dev mode with hot reload
./mvnw quarkus:dev

# Or use Makefile
make dev
```

Quarkus dev mode provides:

- Live reload on code changes
- Dev UI at <http://localhost:8080/q/dev>
- Continuous testing

### Build and Test

```bash
# Build JAR
./mvnw clean package

# Run tests
./mvnw test

# Build native image (requires GraalVM)
./mvnw package -Dnative

# Or use Makefile
make build          # Build JAR
make test           # Run tests
make test-api       # Run API tests
make build-lint     # Build and verify
```

### Docker Commands

```bash
# Start all services
docker compose up --build -d

# View logs
docker compose logs -f api

# Stop services
docker compose down

# Clean up volumes
docker compose down -v

# Or use Makefile
make docker-up      # Start all services
make docker-down    # Stop all services
make docker-logs    # View logs
make docker-build   # Rebuild images
```

## Access Services

| Service        | URL                            | Purpose             |
| -------------- | ------------------------------ | ------------------- |
| Quarkus API    | <http://localhost:8080>        | Main application    |
| Dev UI         | <http://localhost:8080/q/dev>  | Development console |
| Health Check   | <http://localhost:8080/api/health> | Service health  |
| PostgreSQL     | `localhost:5432`               | Database            |
| OTel Collector | <http://localhost:4318>        | Telemetry ingestion |
| OTel Health    | <http://localhost:13133>       | Collector health    |

## Troubleshooting

### Application won't start

```bash
# Check Java version
java -version  # Should be 21+

# Check Maven version
./mvnw -version

# View application logs
docker compose logs api

# Check for port conflicts
lsof -i :8080
```

### Database connection errors

```bash
# Verify PostgreSQL is ready
docker compose exec postgres pg_isready -U postgres

# Check database exists
docker compose exec postgres psql -U postgres -l

# View PostgreSQL logs
docker compose logs postgres
```

### No telemetry data in Scout

```bash
# Check collector health
curl http://localhost:13133/health

# View collector logs
docker compose logs otel-collector

# Verify OTEL configuration
docker compose exec api env | grep OTEL
```

### JWT authentication failing

```bash
# Verify JWT keys exist
ls -la src/main/resources/*.pem

# Regenerate keys
openssl genrsa -out src/main/resources/privateKey.pem 2048
openssl rsa -in src/main/resources/privateKey.pem -pubout -out src/main/resources/publicKey.pem

# Rebuild application
docker compose up --build -d
```

### Native compilation issues

```bash
# Install GraalVM
sdk install java 21.0.1-graalce

# Build native image
./mvnw package -Dnative

# Common issues:
# - Missing native-image tool: Run `gu install native-image`
# - Out of memory: Increase Docker memory to 8GB+
# - Reflection errors: Add reflection config to application
```

## View in Scout

After starting the application and generating some traffic:

1. Log in to [base14 Scout](https://app.base14.io)
2. Navigate to **Services** → **quarkus-postgres-api**
3. View distributed traces, metrics, and logs
4. Explore the service map to see dependencies
5. Analyze JVM metrics and performance

## Resources

- [Quarkus Documentation](https://quarkus.io/guides/)
- [Quarkus OpenTelemetry Guide](https://quarkus.io/guides/opentelemetry)
- [OpenTelemetry Java](https://opentelemetry.io/docs/languages/java/)
- [Quarkus Native Compilation](https://quarkus.io/guides/building-native-image)
- [base14 Scout Documentation](https://docs.base14.io)

