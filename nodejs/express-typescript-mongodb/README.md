# Express.js + TypeScript + MongoDB + OpenTelemetry

A production-ready example demonstrating Express.js 5.x REST API with
TypeScript, MongoDB, and comprehensive OpenTelemetry instrumentation for
end-to-end observability.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/nodejs-express)

## Stack Profile

| Component         | Version  | Status | Notes                             |
| ----------------- | -------- | ------ | --------------------------------- |
| **Node.js**       | 24.x LTS | Active | Krypton - Active until April 2028 |
| **TypeScript**    | 5.7.2    | Latest | Stable                            |
| **Express.js**    | 5.0.1    | Latest | New v5 with improved security     |
| **MongoDB**       | 8.0      | Active | Latest stable                     |
| **Mongoose**      | 8.0.0    | Active | See note below on v9.0.0          |
| **Redis**         | 8.0      | Latest | Alpine variant                    |
| **Socket.io**     | 4.7.2    | Latest | Real-time WebSocket communication |
| **OpenTelemetry** | 0.208.0  | Latest | SDK Node                          |

**Why This Stack**: Demonstrates the latest Express.js 5.x with TypeScript for
type safety, MongoDB for flexible document storage, Socket.io for real-time
updates, and OpenTelemetry for complete observability from HTTP requests through
database operations to WebSocket events.

## Architecture

Layered architecture with clear separation of concerns:

- **API Layer**: Express 5 with `/api/v1/*` versioned routes, CORS,
  Helmet security headers
- **Security**: Rate limiting (100 req/15min global, 5 req/15min auth),
  XSS protection (DOMPurify), JWT authentication with runtime validation
- **Validation**: Zod schemas for type-safe runtime validation and
  TypeScript inference
- **Data**: MongoDB (Mongoose ODM) + Redis (caching & job queue)
- **Background Jobs**: BullMQ for async article publishing with trace
  propagation
- **Real-time**: Socket.IO with JWT authentication for WebSocket updates
- **Observability**: OpenTelemetry automatic instrumentation + custom
  spans/metrics

**Graceful Shutdown**: Coordinated shutdown of HTTP → Socket.IO →
BullMQ → Redis → MongoDB with 10s timeout.

**See detailed architecture**: [docs/architecture.md](./docs/architecture.md)

### ⚠️ Important: Mongoose Version Compatibility

This example uses **Mongoose 8.0.0** with full OpenTelemetry tracing support.

**Note**: Mongoose 9.x is not yet supported by
`@opentelemetry/instrumentation-mongoose` (currently supports `>=5.9.7 <9`).
Track Mongoose 9.x support:
[instrumentation-mongoose](https://github.com/open-telemetry/opentelemetry-js-contrib/tree/main/packages/instrumentation-mongoose)

## What's Instrumented

### Automatic Instrumentation

- ✅ HTTP requests and responses (Express routes and middleware)
- ✅ MongoDB database queries (via Mongoose)
- ✅ Redis operations (via IORedis for BullMQ job queue)
- ✅ WebSocket connections and events (Socket.io)
- ✅ Distributed trace propagation (W3C Trace Context)
- ✅ Background job processing with parent-child trace linking

### Custom Instrumentation

- **Traces**: Business operation spans for CRUD operations, favorites, and
  WebSocket events
- **Attributes**: `article.id`, `article.title`, `article.published`,
  `article.favorites_count`, `user.id`, `socket.id`, pagination details
- **Events**: `article_created`, `article_updated`, `article_deleted`,
  `article_published`, `article_favorited`, `article_unfavorited`,
  `auth_success`, `logout_success`, `client_connected`,
  `subscribed_to_articles`
- **Metrics**: Article operations (created, updated, deleted, published,
  favorited, unfavorited), user operations (login, logout), job queue metrics,
  content size tracking
- **Logs**: Structured logs with trace correlation via Winston
- **Error Tracking**: Exceptions recorded with full context

## Technology Stack

| Package                                     | Version  | Purpose                     |
| ------------------------------------------- | -------- | --------------------------- |
| `express`                                   | ^5.0.1   | Web framework               |
| `mongoose`                                  | ^8.0.0   | MongoDB ODM                 |
| `bullmq`                                    | ^5.65.0  | Background job queue        |
| `ioredis`                                   | ^5.4.2   | Redis client for BullMQ     |
| `bcryptjs`                                  | ^3.0.3   | Password hashing            |
| `jsonwebtoken`                              | ^9.0.3   | JWT authentication          |
| `zod`                                       | ^4.1.13  | Runtime validation          |
| `isomorphic-dompurify`                      | ^2.33.0  | XSS protection              |
| `socket.io`                                 | ^4.7.2   | WebSocket server            |
| `winston`                                   | ^3.17.0  | Structured logging          |
| `typescript`                                | ^5.7.2   | Type safety                 |
| `@opentelemetry/sdk-node`                   | ^0.208.0 | Core SDK                    |
| `@opentelemetry/auto-instrumentations-node` | ^0.52.1  | Auto-instrumentation bundle |
| `@opentelemetry/instrumentation-express`    | ^0.45.0  | Express instrumentation     |
| `@opentelemetry/instrumentation-http`       | ^0.55.0  | HTTP instrumentation        |
| `@opentelemetry/instrumentation-mongoose`   | ^0.44.0  | Mongoose instrumentation    |
| `@opentelemetry/instrumentation-ioredis`    | ^0.45.0  | Redis instrumentation       |
| `@opentelemetry/exporter-trace-otlp-http`   | ^0.208.0 | OTLP HTTP exporter          |
| `@opentelemetry/exporter-metrics-otlp-http` | ^0.208.0 | Metrics exporter            |
| `@opentelemetry/api`                        | ^1.9.0   | OpenTelemetry API           |

## Prerequisites

1. **Docker & Docker Compose** - For running services
2. **base14 Scout Account** - For viewing traces (or use local Jaeger)
3. **Node.js 24+** (optional) - For local development

## Quick Start

### 1. Clone and Navigate

```bash
git clone https://github.com/base-14/examples.git
cd examples/nodejs/express-typescript-mongodb
```

### 2. Set base14 Scout Credentials

Create a `.env.local` file with your Scout credentials:

```bash
cat > .env.local << EOF
SCOUT_ENDPOINT=https://your-tenant.base14.io:4318
SCOUT_CLIENT_ID=your_client_id
SCOUT_CLIENT_SECRET=your_client_secret
SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
EOF
```

> **Note**: See [base14 Scout Setup Guide](https://docs.base14.io/scout/setup)
> for obtaining credentials.

### 3. Start Services

```bash
docker compose up --build
```

This starts:

- Express.js application on port 3000
- MongoDB on port 27017
- Redis on port 6379
- OpenTelemetry Collector on ports 4317/4318

### 4. Test the API

```bash
./scripts/test-api.sh
```

Expected output:

```text
=== Express.js + MongoDB + OpenTelemetry API Testing Script ===

[1/11] Testing health endpoint...
✓ GET /api/health - Health check passed

[2/11] Registering new user...
✓ POST /api/auth/register - User registered

[3/11] Logging in...
✓ POST /api/auth/login - Login successful

...

Passed: 11/11
Failed: 0/11

All tests passed! ✓
```

### 5. View Traces

1. Log into your base14 Scout dashboard
2. Navigate to TraceX
3. You should see traces for:
   - HTTP requests (`GET /api/articles`, `POST /api/articles/:id`)
   - Custom business operations (`article.create`, `article.list`)
   - MongoDB queries (automatic instrumentation)

## Configuration

### Required Environment Variables

| Variable              | Description                | Default | Required |
| --------------------- | -------------------------- | ------- | -------- |
| `SCOUT_ENDPOINT`      | base14 Scout OTLP endpoint | -       | ✅ Yes    |
| `SCOUT_CLIENT_ID`     | Scout OAuth2 client ID     | -       | ✅ Yes    |
| `SCOUT_CLIENT_SECRET` | Scout OAuth2 client secret | -       | ✅ Yes    |
| `SCOUT_TOKEN_URL`     | Scout OAuth2 token URL     | -       | ✅ Yes    |

### Application Environment Variables

| Variable                      | Description                          | Default                                    |
| ----------------------------- | ------------------------------------ | ------------------------------------------ |
| `NODE_ENV`                    | Environment (development/production) | `development`                              |
| `APP_PORT`                    | Application port                     | `3000`                                     |
| `APP_VERSION`                 | Application version                  | `1.0.0`                                    |
| `MONGODB_URI`                 | MongoDB connection string            | `mongodb://mongo:27017/express-app`        |
| `REDIS_URL`                   | Redis connection for BullMQ jobs     | `redis://redis:6379`                       |
| `JWT_SECRET`                  | JWT signing secret (change in prod)  | `your-secret-key-change-in-production`     |
| `JWT_EXPIRES_IN`              | JWT token expiration time            | `7d`                                       |
| `CORS_ORIGIN`                 | CORS allowed origins                 | `*` (all origins)                          |
| `RATE_LIMIT_WINDOW_MS`        | Rate limit window (milliseconds)     | `900000` (15 minutes)                      |
| `RATE_LIMIT_MAX`              | Max requests per window              | `100`                                      |
| `OTEL_SERVICE_NAME`           | Service name in traces               | `express-mongodb-app`                      |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint              | `http://otel-collector:4318`               |
| `OTEL_RESOURCE_ATTRIBUTES`    | Additional resource attributes       | See `.env.example`                         |

## API Endpoints

### Health & Metrics

| Method | Endpoint       | Description                              | Auth Required |
| ------ | -------------- | ---------------------------------------- | ------------- |
| `GET`  | `/api/health`  | Health check with database/Redis status  | No            |
| `GET`  | `/api/metrics` | Prometheus-compatible metrics (OTLP)     | No            |

### Authentication

| Method | Endpoint                | Description      | Auth Required |
| ------ | ----------------------- | ---------------- | ------------- |
| `POST` | `/api/v1/auth/register` | Register user    | No            |
| `POST` | `/api/v1/auth/login`    | Login user       | No            |
| `POST` | `/api/v1/auth/logout`   | Logout user      | Yes           |
| `GET`  | `/api/v1/auth/me`       | Get current user | Yes           |

### Articles

| Method   | Endpoint                        | Description                   | Auth Required |
| -------- | ------------------------------- | ----------------------------- | ------------- |
| `GET`    | `/api/v1/articles`              | List all articles (paginated) | No            |
| `POST`   | `/api/v1/articles`              | Create new article            | Yes           |
| `GET`    | `/api/v1/articles/:id`          | Get single article            | No            |
| `PUT`    | `/api/v1/articles/:id`          | Update article                | Yes           |
| `DELETE` | `/api/v1/articles/:id`          | Delete article                | Yes           |
| `POST`   | `/api/v1/articles/:id/publish`  | Publish article (background)  | Yes           |

### Favorites

| Method   | Endpoint                        | Description          | Auth Required |
| -------- | ------------------------------- | -------------------- | ------------- |
| `POST`   | `/api/v1/articles/:id/favorite` | Favorite an article  | Yes           |
| `DELETE` | `/api/v1/articles/:id/favorite` | Unfavorite article   | Yes           |

### WebSocket Events

The application provides real-time article updates via WebSocket (Socket.io).

**Connection**: `ws://localhost:3000`

**Authentication**: JWT token required (via `auth.token` handshake parameter or
`Authorization` header)

**Client Events** (emit from client):

| Event                  | Description                  | Payload |
| ---------------------- | ---------------------------- | ------- |
| `subscribe:articles`   | Subscribe to article updates | None    |
| `unsubscribe:articles` | Unsubscribe from updates     | None    |

**Server Events** (listen from server):

| Event               | Description              | Payload                                          |
| ------------------- | ------------------------ | ------------------------------------------------ |
| `connected`         | Connection acknowledged  | `{ message, userId }`                            |
| `subscribed`        | Subscription confirmed   | `{ channel }`                                    |
| `unsubscribed`      | Unsubscription confirmed | `{ channel }`                                    |
| `article:created`   | New article created      | `{ id, title, authorId, published, timestamp }`  |
| `article:updated`   | Article updated          | `{ id, title, authorId, published, timestamp }`  |
| `article:deleted`   | Article deleted          | `{ id, title, authorId, timestamp }`             |
| `article:published` | Article published        | `{ id, title, authorId, published, timestamp }`  |

## Example Requests

### Health Check Endpoint

```bash
curl http://localhost:3000/api/health
```

Response:

```json
{
  "status": "healthy",
  "timestamp": "2025-12-03T10:30:00.000Z",
  "service": "express-mongodb-app",
  "version": "1.0.0",
  "database": {
    "connected": true
  }
}
```

### Create Article

```bash
curl -X POST http://localhost:3000/api/articles \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Getting Started with Express.js",
    "content": "A comprehensive guide to building APIs with Express.js and TypeScript",
    "tags": ["express", "typescript", "api"]
  }'
```

Response:

```json
{
  "_id": "674fa2c9e1d2c3f4a5b6c7d9",
  "title": "Getting Started with Express.js",
  "content": "A comprehensive guide...",
  "tags": ["express", "typescript", "api"],
  "published": false,
  "viewCount": 0,
  "createdAt": "2025-12-03T10:30:15.123Z",
  "updatedAt": "2025-12-03T10:30:15.123Z"
}
```

### List Articles

```bash
curl "http://localhost:3000/api/articles?page=1&limit=10"
```

Response:

```json
{
  "articles": [...],
  "pagination": {
    "page": 1,
    "limit": 10,
    "total": 25,
    "pages": 3
  }
}
```

### Get Article

```bash
curl http://localhost:3000/api/articles/674fa2c9e1d2c3f4a5b6c7d9
```

### Update Article

```bash
curl -X PUT http://localhost:3000/api/articles/674fa2c9e1d2c3f4a5b6c7d9 \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated Title",
    "content": "Updated content"
  }'
```

### Delete Article

```bash
curl -X DELETE http://localhost:3000/api/articles/674fa2c9e1d2c3f4a5b6c7d9
```

### WebSocket Client Examples

#### HTML Client

Open `examples/websocket-client.html` in your browser:

1. First, obtain a JWT token by logging in via the API
2. Paste the token in the input field
3. Click "Connect" to establish WebSocket connection
4. Click "Subscribe to Articles" to start receiving updates
5. Perform article operations (create, update, delete, publish) via the API
6. Watch real-time events appear in the browser

#### Node.js Client

```bash
# First, get a JWT token
TOKEN=$(curl -s -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}' | jq -r '.token')

# Install socket.io-client
npm install socket.io-client

# Run the WebSocket client
JWT_TOKEN=$TOKEN node examples/websocket-client.js
```

Expected output:

```text
Connecting to http://localhost:3000...
✓ Connected to WebSocket server
Socket ID: abc123xyz
✓ Server acknowledged connection
User ID: 674fa2c9e1d2c3f4a5b6c7d9
Message: Connected to article updates
✓ Subscribed to channel: articles
Listening for article updates...

📝 ARTICLE CREATED
   ID: 674fa2c9e1d2c3f4a5b6c7d9
   Title: New Article Title
   Author: 674fa2c9e1d2c3f4a5b6c7d8
   Published: false
   Timestamp: 12/4/2025, 3:30:00 AM
```

## Telemetry Data

### Traces

**HTTP Spans** (automatic):

- Span name: `GET /api/articles`, `POST /api/articles`, etc.
- Attributes: `http.method`, `http.route`, `http.status_code`, `http.target`

**Database Spans** (automatic):

- Span name: `mongodb.find`, `mongodb.insertOne`, etc.
- Attributes: `db.system=mongodb`, `db.operation`, `db.mongodb.collection`

**Custom Business Spans**:

- `article.create` - Article creation operation
- `article.list` - List articles with pagination
- `article.get` - Get single article
- `article.update` - Update article
- `article.delete` - Delete article

**Custom Attributes**:

- `article.id` - Article MongoDB ObjectId
- `article.title` - Article title
- `article.published` - Publication status
- `article.list.page` - Current page number
- `article.list.limit` - Page size
- `article.list.total` - Total article count

**Custom Events**:

- `article_created` - Fired after successful article creation
- `article_updated` - Fired after successful update
- `article_deleted` - Fired after successful deletion

### Example Trace

A typical `POST /api/articles` trace includes:

```text
HTTP POST /api/articles                    [Auto-instrumented]
 └─ article.create                         [Custom span]
     └─ mongodb.insertOne                  [Auto-instrumented]
```

### Metrics

Automatic metrics collected:

- HTTP request duration histogram
- HTTP request count by route
- MongoDB operation duration
- System runtime metrics (memory, CPU)

## OpenTelemetry Configuration

### SDK Initialization

The OpenTelemetry SDK is initialized in `src/telemetry.ts` before the Express
app is loaded:

```typescript
// src/index.ts
import { setupTelemetry } from "./telemetry";

// MUST initialize telemetry FIRST
setupTelemetry();

// Then import Express app
import { createApp } from "./app";
```

**Key Configuration** (`src/telemetry.ts`):

- Resource attributes: service name, version, environment
- Auto-instrumentations: HTTP, Express, MongoDB
- OTLP HTTP exporter for traces and metrics
- Graceful shutdown on SIGTERM

### Custom Instrumentation Example

See `src/controllers/article.controller.ts:17-50` for the full pattern:

```typescript
import {
  trace,
  SpanStatusCode,
  context as otelContext,
} from "@opentelemetry/api";

const tracer = trace.getTracer("article-controller");

export async function createArticle(
  req: Request,
  res: Response,
): Promise<void> {
  const span = tracer.startSpan("article.create");

  try {
    await otelContext.with(
      trace.setSpan(otelContext.active(), span),
      async () => {
        const article = await Article.create({ title, content, tags });

        span.setAttributes({
          "article.id": article.id,
          "article.title": article.title,
        });

        span.addEvent("article_created", {
          "article.id": article.id,
        });

        span.setStatus({ code: SpanStatusCode.OK });
        res.status(201).json(article);
      },
    );
  } catch (error) {
    span.recordException(error as Error);
    span.setStatus({ code: SpanStatusCode.ERROR, message: error.message });
    throw error;
  } finally {
    span.end();
  }
}
```

**Pattern breakdown**:

1. Create tracer for the controller
2. Start custom span with descriptive name
3. Wrap async work in active context
4. Set custom attributes and events
5. Record exceptions and set error status
6. Always end span in `finally` block

## Database Schema

### Articles Collection

```typescript
{
  _id: ObjectId,              // MongoDB document ID
  title: string,              // Article title (max 200 chars)
  content: string,            // Article content (max 50000 chars)
  tags: string[],             // Array of tags
  published: boolean,         // Publication status (default: false)
  publishedAt?: Date,         // Publication timestamp
  viewCount: number,          // View counter (default: 0)
  createdAt: Date,            // Auto-generated
  updatedAt: Date             // Auto-generated
}
```

**Indexes**:

- Text index on `title` for search
- Compound index: `{ published: 1, createdAt: -1 }` for efficient queries

## Development

### Local Build

```bash
npm install
npm run build
npm start
```

### Testing

**Test suite** with **74.31% coverage** (181 tests):

```bash
npm test                 # All tests
npm run test:unit        # Unit tests only
npm run test:integration # Integration tests
npm run test:e2e         # End-to-end tests
npm run test:coverage    # With coverage report

./scripts/test-api.sh    # API smoke test (17 scenarios)
```

**Test scenarios** include:

- ✅ Success: Valid requests, auth, CRUD operations, favorites
- ❌ Failures: Invalid input, XSS attempts, validation errors, rate limiting

See [Testing Guide](./docs/testing.md) for writing tests.

### Docker Commands

```bash
# Build and start all services
docker compose up --build

# Stop services
docker compose down

# View logs
docker compose logs -f app

# Rebuild after code changes
docker compose up --build app
```

### Access Services

| Service               | URL                                   | Purpose             |
| --------------------- | ------------------------------------- | ------------------- |
| Express API           | <http://localhost:3000>               | Main application    |
| Health Check          | <http://localhost:3000/api/health>    | Service health      |
| WebSocket             | ws://localhost:3000                   | Real-time updates   |
| MongoDB               | mongodb://localhost:27017             | Database            |
| Redis                 | redis://localhost:6379                | Job queue           |
| OTel Collector (gRPC) | <http://localhost:4317>               | Telemetry ingestion |
| OTel Collector (HTTP) | <http://localhost:4318>               | Telemetry ingestion |
| OTel zPages           | <http://localhost:55679/debug/tracez> | Debug traces        |
| OTel Health Check     | <http://localhost:13133>              | Collector health    |

## Troubleshooting

### No traces appearing in Scout

1. **Check collector logs**:

   ```bash
   docker logs otel-collector
   ```

   Look for authentication errors or export failures.

2. **Verify Scout credentials** in `.env.local`:

   ```bash
   echo $SCOUT_ENDPOINT
   echo $SCOUT_CLIENT_ID
   ```

3. **Check local traces** in collector debug output:

   ```bash
   docker logs otel-collector 2>&1 | grep "Span"
   ```

4. **Verify app is sending telemetry**:

   ```bash
   curl http://localhost:13133
   # Should return collector health status
   ```

### Database connection errors

1. **Check MongoDB health**:

   ```bash
   docker logs express-mongodb
   ```

2. **Verify MongoDB is ready**:

   ```bash
   docker exec express-mongodb mongosh --eval "db.adminCommand('ping')"
   ```

3. **Check connection string** in compose.yml matches `.env` settings

### Application won't start

1. **Check TypeScript compilation**:

   ```bash
   npm run build
   ```

2. **View application logs**:

   ```bash
   docker logs express-mongodb-app
   ```

3. **Verify port 3000 is available**:

   ```bash
   lsof -i :3000
   ```

### WebSocket connection issues

1. **Check authentication**:
   - Verify JWT token is valid and not expired
   - Ensure token is passed in `auth.token` handshake parameter

2. **Check server logs**:

   ```bash
   docker logs express-mongodb-app | grep socket
   ```

3. **Test connection with HTML client**:
   - Open `examples/websocket-client.html` in browser
   - Check browser console for connection errors

## Resources

- [OpenTelemetry JavaScript Documentation](https://opentelemetry.io/docs/languages/js/)
- [Express.js Documentation](https://expressjs.com/)
- [Mongoose Documentation](https://mongoosejs.com/)
- [base14 Scout Documentation](https://docs.base14.io/)
- [TypeScript Documentation](https://www.typescriptlang.org/)

## License

MIT
