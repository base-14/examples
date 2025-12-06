# OpenTelemetry Telemetry Verification Guide

This guide helps you verify complete OpenTelemetry instrumentation for the
Express + TypeScript + MongoDB application by walking through all 17 test
scenarios in `scripts/test-api.sh`.

## Signal-Specific Guides

For quick reference on each observability signal:

- **[Traces](./traces-verification.md)** - Span patterns, instrumentation
  scopes, trace propagation
- **[Logs](./logs-verification.md)** - Log levels, components, trace
  correlation
- **[Metrics](./metrics-verification.md)** - Custom & auto-instrumentation
  metrics

## Quick Reference

### What to Check for Each Request

For every API request, verify the following telemetry components:

1. **Trace Hierarchy** - Proper parent-child span relationships
2. **Span Attributes** - Semantic conventions and business context
3. **Log Correlation** - Logs include matching trace_id and span_id
4. **Span Events** - Key business events captured
5. **Resource Attributes** - Service metadata (name, version, environment)

---

## Verification Checklist by Request Type

### 1. Health Check (`GET /api/health`)

**Expected Spans:**

```text
GET (root)
├─ mongodb.ping (DB health check)
└─ redis.ping (Cache health check)
```text

**Key Attributes to Verify:**

- ✅ `http.status_code: 200`
- ✅ `db.system: mongodb` and `db.system: redis`
- ✅ `db.operation: ping`
- ✅ All spans have same `trace_id`

**Expected Logs:** None (successful health checks don't log)

---

### 2. Validation Error (`POST /api/v1/auth/register` - invalid email)

**Expected Spans:**

```text
POST (root)
└─ (no controller span - rejected at middleware)
```text

**Key Attributes to Verify:**

- ✅ `http.status_code: 400`
- ✅ `http.method: POST`
- ✅ Single HTTP span only (early rejection)

**Expected Logs:**

```text
[warn] [error-handler][trace_id=xxx]: Request error
{
  "path": "/api/v1/auth/register",
  "statusCode": 400,
  "code": "VALIDATION_ERROR",
  "error": "email: Invalid email format, ...",
  "deployment.environment": "development"
}
```text

**Verification Points:**

- ✅ Log has `trace_id` matching span
- ✅ Log includes `deployment.environment`
- ✅ Error message describes validation failure

---

### 3. Successful Registration (`POST /api/v1/auth/register`)

**Expected Spans:**

```text
POST (root)
└─ auth.register (controller)
   ├─ mongodb.find (check existing user)
   └─ mongodb.insert (create user)
```text

**Key Attributes to Verify:**

- ✅ `http.status_code: 201`
- ✅ `auth.register` span: `Status: Ok`
- ✅ `mongodb.find`: `db.mongodb.collection: users`, `db.operation: find`
- ✅ `mongodb.insert`: `db.mongodb.collection: users`, `db.operation: insert`
- ✅ `db.statement`: Sensitive data masked with `?` placeholders

**Expected Logs:**

```text
[info] [auth-controller][trace_id=xxx]: User registered successfully
{
  "user.id": "...",
  "user.email": "...",
  "user.role": "user",
  "deployment.environment": "development"
}
```text

**Verification Points:**

- ✅ Complete span hierarchy (3 spans)
- ✅ Log `span_id` matches `auth.register` span
- ✅ No passwords in traces/logs
- ✅ Email in `db.statement` replaced with `?`

---

### 4. Login Failed - Wrong Password (`POST /api/v1/auth/login`)

**Expected Spans:**

```text
POST (root)
└─ auth.login (controller)
   └─ mongodb.find (lookup user)
```text

**Key Attributes to Verify:**

- ✅ `http.status_code: 401`
- ✅ `auth.login` span: `Status: Error`, `Status Message: Invalid credentials`
- ✅ `user.id` and `reason: invalid_password` in span attributes

**Expected Logs:**

```text
[warn] [auth-controller][trace_id=xxx]: Login failed - invalid password
{
  "user.id": "...",
  "user.email": "...",
  "reason": "invalid_password",
  "deployment.environment": "development"
}

[warn] [error-handler][trace_id=xxx]: Request error
{
  "path": "/api/v1/auth/login",
  "statusCode": 401,
  "code": "AUTH_REQUIRED",
  "error": "Invalid credentials"
}
```text

**Verification Points:**

- ✅ Span status is `Error` (not `Ok`)
- ✅ Two log entries (controller + error handler)
- ✅ Both logs have same `trace_id`
- ✅ No password in traces/logs

---

### 5. Login Success (`POST /api/v1/auth/login`)

**Expected Spans:**

```text
POST (root)
└─ auth.login (controller)
   └─ mongodb.find (lookup user)
```text

**Key Attributes to Verify:**

- ✅ `http.status_code: 200`
- ✅ `auth.login` span: `Status: Ok` (compare with failed login!)
- ✅ `user.id`, `user.email`, `user.role` in span

**Expected Logs:**

```text
[info] [auth-controller][trace_id=xxx]: User logged in successfully
{
  "user.id": "...",
  "user.email": "...",
  "deployment.environment": "development"
}
```text

**Verification Points:**

- ✅ Span status is `Ok` (vs `Error` for wrong password)
- ✅ No JWT token in traces/logs
- ✅ Log correlation intact

---

### 6. Authenticated Request (`GET /api/v1/auth/me`)

**Expected Spans:**

```text
GET (root) ← has user.* attributes from JWT middleware!
├─ auth.me (controller)
└─ mongodb.find (user lookup by ID)
```text

**Key Attributes to Verify:**

- ✅ HTTP span has `user.id`, `user.email`, `user.role` (from JWT middleware)
- ✅ `mongodb.find`: `db.statement` filters by `_id` (not `email`)
- ✅ `auth.me` span has `InstrumentationScope: auth-controller`

**Expected Logs:** None (successful read operations don't log)

**Verification Points:**

- ✅ User context enriches HTTP span (JWT middleware)
- ✅ Database query uses `_id` filter
- ✅ No JWT token in traces

---

### 7. Authentication Failure - Missing Token (`POST /api/v1/articles`)

**Expected Spans:**

```text
POST (root)
├─ SpanEvent: auth_failed (reason: missing_token)
└─ (no controller span - rejected at auth middleware)
```text

**Key Attributes to Verify:**

- ✅ `http.status_code: 401`
- ✅ SpanEvent with `reason: missing_token`
- ✅ Single HTTP span only

**Expected Logs:**

```text
[warn] [auth-middleware][trace_id=xxx]: Authentication failed - missing token
{
  "path": "/api/v1/articles",
  "method": "POST",
  "ip": "...",
  "reason": "missing_token",
  "deployment.environment": "development"
}
```text

**Verification Points:**

- ✅ Span event on HTTP span (not separate span)
- ✅ Log includes IP address for security monitoring
- ✅ No downstream operations (efficient rejection)

---

### 8. Authentication Failure - Invalid Token

**Expected Spans:**

```text
POST (root)
├─ SpanEvent: auth_failed (reason: invalid_token)
└─ (no controller span)
```text

**Expected Logs:**

```text
[warn] [auth-middleware][trace_id=xxx]: Authentication failed -
  invalid or expired token
{
  "path": "/api/v1/articles",
  "method": "POST",
  "ip": "...",
  "reason": "invalid_token",
  "error": "Invalid token",
  "deployment.environment": "development"
}
```text

**Verification Points:**

- ✅ Log includes `error` field with JWT error message
- ✅ No token value in logs/traces
- ✅ Span event captures failure reason

---

### 9. XSS Sanitization (`POST /api/v1/articles` with script tags)

**Expected Behavior:**

- Script tags removed from `title` and `tags`
- Safe HTML preserved in `content` field
- If title becomes empty after sanitization → validation error

**Expected Spans:**

```text
POST (root)
└─ mongodb.find (auth user lookup)
   └─ Either validation error (400) OR article.create (201)
```text

**Key Attributes to Verify:**

- ✅ Article title/content in spans have XSS removed
- ✅ `article.title` shows sanitized value (e.g., "Safe Title with")
- ✅ No `<script>`, `onerror`, or other XSS vectors in traces

**Verification Points:**

- ✅ XSS removed before Zod validation
- ✅ Safe HTML tags (`<p>`, `<strong>`) preserved in content
- ✅ No malicious code in database or telemetry

---

### 10. Validation Error - Missing Field (`POST /api/v1/articles`)

**Expected Spans:**

```text
POST (root)
└─ mongodb.find (auth user lookup only)
   └─ (no controller span - rejected at validation middleware)
```text

**Key Attributes to Verify:**

- ✅ `http.status_code: 400`
- ✅ Only 2 spans (HTTP + auth DB lookup)

**Expected Logs:**

```text
[warn] [error-handler][trace_id=xxx]: Request error
{
  "path": "/api/v1/articles",
  "statusCode": 400,
  "code": "VALIDATION_ERROR",
  "error": "content: Invalid input: expected string, received undefined",
  "deployment.environment": "development"
}
```text

**Verification Points:**

- ✅ Early rejection (no controller/DB operations)
- ✅ Clear field-level error message
- ✅ Multiple errors combined (e.g., "title: ..., content: ...")

---

### 11. Successful Article Creation (`POST /api/v1/articles`)

**Expected Spans:**

```text
POST (root)
├─ mongodb.find (auth user lookup)
└─ article.create (controller)
   ├─ mongodb.insert (create article)
   └─ socket.emit_article_event
      └─ send / (Socket.IO message)
```text

**Key Attributes to Verify:**

- ✅ `http.status_code: 201`
- ✅ `article.id`, `article.title`, `article.author_id` in controller span
- ✅ Socket.IO span: `Kind: Internal`, child has `Kind: Producer`
- ✅ `messaging.socket.io.event_name: article:created`
- ✅ `mongodb.insert`: `db.mongodb.collection: articles`

**Expected Logs:**

```text
[info] [socket-emitter][trace_id=xxx]: Article event emitted
{
  "event": "article:created",
  "articleId": "...",
  "articleTitle": "...",
  "deployment.environment": "development"
}
```text

**Span Events:**

```text
SpanEvent: article_created
  - article.id: ...
  - article.tags_count: 2

SpanEvent: event_emitted
  - event.name: article:created
  - article.id: ...
```text

**Verification Points:**

- ✅ Complete flow: HTTP → Auth → Controller → DB → Socket.IO
- ✅ WebSocket message traced with Producer span
- ✅ Real-time event correlation with article creation
- ✅ Sanitized data in all telemetry

**Expected Metrics Updates:**

```text
articles.created.total (Counter)
  Attributes: user.id=<user-id>
  Value: Incremented by 1

article.content.size (Histogram)
  Attributes: article.id=<article-id>
  Count: 1
  Sum: <content-length>

http.server.duration (Histogram)
  Attributes: http.method=POST, http.status_code=201
  Bucket updated with request duration

db.client.connections.usage (Gauge)
  state=idle: 3 (connections available)
  state=used: 0 (after request completes)
```text

**Metric Verification Commands:**

```bash
# Check articles.created counter
docker logs otel-collector 2>&1 | grep -A 10 "articles.created.total" | grep -E "(Value:|user.id)"

# Check article content size histogram
docker logs otel-collector 2>&1 | grep -A 15 "article.content.size" | grep -E "(Count:|Sum:|article.id)"

# Check HTTP duration for 201 responses
docker logs otel-collector 2>&1 | grep -A 5 "http.server.duration" | \
  grep "status_code: Int(201)"
```text

---

### 12. Get Article with Invalid ID (`GET /api/v1/articles/invalid123`)

**Expected Spans:**

```text
GET (root)
└─ article.get (controller with Error status)
```text

**Key Attributes to Verify:**

- ✅ `http.status_code: 400` (not 500!)
- ✅ Controller span: `Status: Error`
- ✅ Controller span: Status Message contains Mongoose error
- ✅ `article.id: invalid123` in controller span
- ✅ **No database span** - error caught before DB query

**Expected Logs:**

```text
[warn] [error-handler][trace_id=xxx]: Invalid ID format
{
  "path": "/api/v1/articles/invalid123",
  "method": "GET",
  "value": "invalid123",
  "kind": "ObjectId",
  "deployment.environment": "development"
}
```text

**Verification Points:**

- ✅ CastError caught and converted to 400 (not 500)
- ✅ Controller span created and marked with Error status
- ✅ Status message includes full Mongoose error details
- ✅ No database query executed (efficient early rejection)
- ✅ User-friendly error message in response
- ✅ Technical error details in span (not exposed to client)
- ✅ Structured error log with context (path, method, value, kind)
- ✅ Log correlation intact

**Expected Metrics Updates:**

```text
http.server.duration (Histogram)
  Attributes: http.method=GET, http.status_code=400
  Bucket updated with request duration

db.client.connections.usage (Gauge)
  No change (no DB query made)
```text

**Key Distinction:**

- **400 Invalid ID** (Step 12) - Malformed ObjectId, caught before DB
- **404 Not Found** - Valid ObjectId format, but article doesn't exist
  (requires DB query)

**Error Flow:**

```text
GET /api/v1/articles/invalid123
  → Controller: article.get span
    → Mongoose: Cast "invalid123" to ObjectId
      → CastError thrown
        → Error Middleware: Catch CastError
          → Span Status: Error
          → Log: WARN level
          → Response: 400 Bad Request
```text

---

### 13. List Articles with Pagination (`GET /api/v1/articles?page=1&limit=10`)

**Expected Spans:**

```text
GET (root - no user.* attributes, public endpoint)
└─ article.list (controller)
   ├─ mongodb.aggregate (count total articles)
   └─ mongodb.find (fetch paginated results)
```text

**Key Attributes to Verify:**

- ✅ `http.status_code: 200`
- ✅ **No user.* attributes** on HTTP span (public endpoint, no auth)
- ✅ Controller span: `article.list.page`, `article.list.limit`,
  `article.list.total`, `article.list.returned`
- ✅ **Two DB spans**: aggregate (count) + find (paginated fetch)
- ✅ `mongodb.aggregate`: `db.operation: aggregate` with `$match` and `$group` pipeline
- ✅ `mongodb.find`: `db.operation: find` with `skip` and `limit` parameters

**Expected Logs:**

```text
(no logs for successful read operations)
```text

**Verification Points:**

- ✅ Public endpoint requires no authentication
- ✅ Two database queries traced (count + fetch)
- ✅ Pagination metadata captured in controller span
- ✅ Aggregate pipeline structure visible in db.statement
- ✅ Skip/limit parameters visible in find query
- ✅ Empty filter `{}` shows no filtering applied
- ✅ Total vs returned articles tracked separately
- ✅ Query parameters (page, limit) validated by Zod

**Expected Metrics Updates:**

```text
http.server.duration (Histogram)
  Attributes: http.method=GET, http.status_code=200
  Bucket updated with request duration

db.client.connections.usage (Gauge)
  state=idle: 3 (after both queries complete)
```text

**Database Operations:**

**Operation 1: Count Total (mongodb.aggregate)**

```json
{
  "aggregate": "?",
  "pipeline": [
    {"$match": {}},
    {"$group": {"_id": "?", "n": {"$sum": "?"}}}
  ]
}
```text

Purpose: Calculate total articles for pagination metadata

**Operation 2: Fetch Page (mongodb.find)**

```json
{
  "find": "?",
  "filter": {},
  "sort": {},
  "skip": "?",
  "limit": "?"
}
```text

Purpose: Retrieve articles for current page

**Pagination Attributes:**

- `article.list.page: 1` - Current page number (from query param)
- `article.list.limit: 10` - Items per page (from query param)
- `article.list.total: 3` - Total items in database (from aggregate)
- `article.list.returned: 3` - Items in this response (from find)

**Performance Insights:**

- Two DB queries required for pagination (count + fetch)
- Count uses `$match:{}` (scans entire collection)
- High `skip` values (deep pagination) cause slower queries
- Both queries visible in trace with individual timings

**Comparison: Authenticated vs Public:**

| Aspect | Authenticated Endpoint | Public Endpoint (Step 13) |
|--------|------------------------|---------------------------|
| user.* attributes | ✅ Present | ❌ Absent |
| Auth DB query | ✅ mongodb.find (user) | ❌ None |
| Total spans | 3-4 | 3 (HTTP + controller + 2 DB) |

---

### 14. Update Article Without Auth (`PUT /api/v1/articles/:id`)

**Pattern:** Same as Step 8 (Authentication Failure - Missing Token)

**Expected Telemetry:**

```text
PUT (root span only)
├─ http.method: PUT
├─ http.status_code: 401
└─ SpanEvent: auth_failed (reason: missing_token)

Log: [warn] [auth-middleware] Authentication failed - missing token
```text

**Key Differences from Step 8:**

- HTTP Method: `PUT` instead of `POST`
- Path: `/api/v1/articles/:id` instead of `/api/v1/articles`
- Telemetry: **Identical** (same span event, same log pattern)

**Verification Points:**

- ✅ Same authentication failure telemetry regardless of HTTP method
- ✅ Same authentication failure telemetry regardless of endpoint path
- ✅ Consistent security event tracking across all protected endpoints
- ✅ Early rejection (no controller or DB spans)

This demonstrates that authentication middleware produces **consistent
telemetry** across different HTTP methods (POST, PUT, DELETE) and different
endpoints, making it easy to detect and monitor unauthorized access attempts.

---

### 15. Update Article with Valid Auth (`PUT /api/v1/articles/:id`)

**Expected Spans:**

```text
PUT (root)
├─ mongodb.find (auth user lookup)
├─ mongodb.find (article ownership verification)
└─ article.update (controller)
   ├─ mongodb.update (update article)
   └─ socket.emit_article_event
      └─ send / (Socket.IO message)
```text

**Key Attributes to Verify:**

- ✅ `http.method: PUT`
- ✅ `http.status_code: 200`
- ✅ `user.id: <user-id>` on HTTP span (authenticated)
- ✅ Controller span: `Status: Ok`
- ✅ Span Event: `article_updated` with article details
- ✅ Socket.IO spans for article:updated event emission

**Database Operations:**

**Operation 1: User Lookup (mongodb.find)**

```json
{
  "find": "?",
  "filter": "?"
}
```text

Purpose: Authenticate user from JWT token

**Operation 2: Article Lookup (mongodb.find)**

```json
{
  "find": "?",
  "filter": "?"
}
```text

Purpose: Verify article exists and user is the author

**Operation 3: Update Article (mongodb.update)**

```json
{
  "update": "?",
  "updates": "?"
}
```text

Purpose: Apply updates to article document

**Expected Logs:**

```text
[info] [socket-emitter][trace_id=xxx]: Article event emitted
{
  "event": "article:updated",
  "articleId": "6933d7ef23bf2349948546b0",
  "articleTitle": "Getting Started with OpenTelemetry - Updated Edition",
  "deployment.environment": "development"
}
```text

**Verification Points:**

- ✅ Three separate database queries (auth + ownership check + update)
- ✅ Controller span contains article_updated event with full details
- ✅ Socket.IO event emitted to notify connected clients
- ✅ Real-time update propagation via WebSocket
- ✅ User context propagated through entire trace
- ✅ Successful update logged with article details

**Expected Metrics Updates:**

```text
http.server.duration (Histogram)
  Attributes: http.method=PUT, http.status_code=200
  Bucket updated with request duration

db.client.connections.usage (Gauge)
  Updated during three DB operations
```text

**Business Event Details:**
The `article_updated` span event captures:

- `article.id` - Updated article ID
- `article.title` - New article title
- `article.author_id` - Author performing the update

**Socket.IO Flow:**

1. Article updated successfully in database
2. Controller creates socket.emit_article_event span
3. Event emitted with event_emitted span event
4. Socket.IO sends message (send / span)
5. Connected clients receive article:updated event in real-time

---

### 16. Publish Article - Async Job with Trace Propagation (`POST /api/v1/articles/:id/publish`)

**Expected Spans - HTTP Request:**

```text
POST (root) - Enqueue job
├─ mongodb.find (auth user lookup)
├─ mongodb.find (article verification)
└─ article.publish (controller)
   └─ evalsha (Redis - BullMQ enqueue job)
```text

**Expected Spans - Background Worker:**

```text
job.publishArticle.process (root with propagated trace)
├─ mongodb.find (fetch article)
├─ mongodb.update (set published=true)
└─ socket.emit_article_event
   └─ send / (Socket.IO message)
```text

**Key Attributes to Verify:**

**HTTP Request Span:**

- ✅ `http.method: POST`
- ✅ `http.route: /api/v1/articles/:id/publish`
- ✅ `user.id: <user-id>` (authenticated)
- ✅ Span Event: `job_enqueued` with article.id

**Background Worker Span:**

- ✅ `Kind: Internal`
- ✅ Parent ID matches article.publish controller span
- ✅ `job.id: <job-id>` (e.g., "3")
- ✅ `job.attempt: 0`
- ✅ `article.id: <article-id>`
- ✅ `article.title: <title>`
- ✅ `article.published: true`
- ✅ `job.duration_ms: <duration>`
- ✅ Span Event: `job_started`

**Expected Logs:**

**HTTP Request:**

```text
(No log for successful job enqueue)
```text

**Background Worker:**

```text
[info] [socket-emitter][trace_id=xxx]: Article event emitted
{
  "event": "article:published",
  "articleId": "693406cc23bf2349948546c0",
  "articleTitle": "Getting Started with Express.js 1765017291",
  "deployment.environment": "development"
}
```text

**Verification Points:**

- ✅ HTTP request enqueues job to BullMQ (Redis evalsha operation)
- ✅ HTTP request returns immediately (200 OK) without waiting for job
- ✅ Background worker processes job asynchronously
- ✅ **Trace context propagated** from HTTP request to background worker
- ✅ Background worker span has same trace ID as HTTP request
- ✅ Background worker span has article.publish as parent
- ✅ Article updated in database (published=true)
- ✅ Socket.IO event emitted after background processing
- ✅ Connected clients receive real-time article:published notification

**Expected Metrics Updates:**

```text
http.server.duration (Histogram)
  Attributes: http.method=POST, http.status_code=200
  Bucket updated with request duration (fast - job enqueued, not processed)

job.processing.duration (Histogram) [if implemented]
  Attributes: job.name=publishArticle
  Bucket updated with actual job processing time

articles.published.total (Counter) [if implemented]
  Attributes: article.id=<article-id>
  Value: Incremented by 1

db.client.connections.usage (Gauge)
  Updated during background worker DB operations
```text

**Trace Propagation Flow:**

1. HTTP POST /articles/:id/publish received
2. Controller creates article.publish span
3. Span event `job_enqueued` recorded
4. Job data + **trace context** added to BullMQ
5. Job enqueued to Redis (evalsha span)
6. HTTP response returns (200 OK)
7. Background worker picks up job
8. Worker creates `job.publishArticle.process` span with **propagated trace context**
9. Worker fetches article from DB
10. Worker updates article (published=true)
11. Worker emits Socket.IO event (article:published)
12. Job completes successfully

**Critical Feature - Trace Context Propagation:**

This test verifies that OpenTelemetry trace context is properly propagated
through BullMQ:

- **Same Trace ID**: Background worker span shares trace ID with HTTP
  request
- **Parent-Child Relationship**: Worker span is child of controller span
- **End-to-End Visibility**: Complete request flow visible in single
  distributed trace
- **Async Job Debugging**: Can trace from HTTP request → Redis queue →
  background processing → DB update → Socket.IO event

This allows you to:

- Track the full lifecycle of an async operation
- Measure true end-to-end latency (HTTP response + background processing)
- Debug failures in background jobs with full context
- Understand dependencies between sync and async operations

---

### 17. Delete Article with Valid Auth (`DELETE /api/v1/articles/:id`)

**Expected Spans:**

```text
DELETE (root)
├─ mongodb.find (auth user lookup)
├─ mongodb.find (article ownership verification)
└─ article.delete (controller)
   ├─ mongodb.findAndModify (delete article)
   └─ socket.emit_article_event
      └─ send / (Socket.IO message)
```text

**Key Attributes to Verify:**

- ✅ `http.method: DELETE`
- ✅ `http.target: /api/v1/articles/:id`
- ✅ `user.id: <user-id>` on HTTP span (authenticated)
- ✅ `user.email: <email>` on HTTP span
- ✅ Controller span: `Status: Unset` (successful)
- ✅ Span Event: `article_deleted` with article details
- ✅ Socket.IO spans for article:deleted event emission

**Database Operations:**

**Operation 1: User Lookup (mongodb.find)**

```json
{
  "find": "?",
  "filter": "?"
}
```text

Purpose: Authenticate user from JWT token

**Operation 2: Article Lookup (mongodb.find)**

```json
{
  "find": "?",
  "filter": "?"
}
```text

Purpose: Verify article exists and user is the author

**Operation 3: Delete Article (mongodb.findAndModify)**

```json
{
  "findAndModify": "?",
  "query": "?",
  "remove": true
}
```text

Purpose: Delete article document from database

**Expected Logs:**

```text
[info] [socket-emitter][trace_id=xxx]: Article event emitted
{
  "event": "article:deleted",
  "articleId": "693421df23bf2349948546e0",
  "articleTitle": "Article to Delete 1765024223",
  "deployment.environment": "development"
}
```text

**Verification Points:**

- ✅ Three database queries (auth + ownership check + delete)
- ✅ Controller span contains article_deleted event with full details
- ✅ Socket.IO event emitted to notify connected clients
- ✅ Real-time deletion notification via WebSocket
- ✅ User context propagated through entire trace
- ✅ HTTP 204 No Content response (successful deletion)
- ✅ Article no longer exists in database (verified with GET → 404)

**Expected Metrics Updates:**

```text
http.server.duration (Histogram)
  Attributes: http.method=DELETE, http.status_code=204
  Bucket updated with request duration

articles.deleted.total (Counter) [if implemented]
  Attributes: user.id=<user-id>
  Value: Incremented by 1

articles.total (Gauge) [if implemented]
  Decremented by 1

db.client.connections.usage (Gauge)
  Updated during three DB operations
```text

**Business Event Details:**
The `article_deleted` span event captures:

- `article.id` - Deleted article ID
- `article.title` - Article title (before deletion)
- `user.id` - User performing the deletion
- `article.author_id` - Original article author

**Socket.IO Flow:**

1. Article deleted successfully from database
2. Controller creates socket.emit_article_event span
3. Event emitted with event_emitted span event
4. Socket.IO sends message (send / span)
5. Connected clients receive article:deleted event in real-time
6. Clients can remove the article from their UI

**HTTP 204 No Content:**

- No response body (empty)
- Success indicated by status code only
- Standard for successful DELETE operations

---

## General Verification Patterns

### Trace Hierarchy Rules

1. **Root Span**: Always an HTTP span (`Kind: Server`)
2. **Database Spans**: `Kind: Client`, parent is controller or HTTP span
3. **Controller Spans**: `Kind: Internal`, parent is HTTP span
4. **Socket.IO Emit**: `Kind: Internal`, child is `Kind: Producer`

### Log Correlation

Every log entry must have:

- ✅ `trace_id` - matches all spans in the trace
- ✅ `span_id` - matches the span where log originated
- ✅ `component` - identifies logger (e.g., "auth-controller",
  "error-handler")
- ✅ `deployment.environment` - environment identifier

### Metrics Verification

**Three Signal Correlation** - For every operation, verify all three
observability signals:

1. **Traces** - Distributed request flow with timing
2. **Logs** - Contextual events with structured data
3. **Metrics** - Aggregated measurements over time

**Metrics Categories:**

**Auto-Instrumentation Metrics (Always Present):**

- ✅ `http.server.duration` - HTTP request latency histogram
- ✅ `db.client.connections.usage` - Database connection pool state
- ✅ `nodejs.eventloop.delay.*` - Node.js event loop performance
- ✅ `v8js.memory.heap.used` - V8 memory usage
- ✅ `v8js.gc.duration` - Garbage collection timing

**Custom Application Metrics (Business Logic):**

- ✅ `users.registered.total` - Counter with user.role attribute
- ✅ `users.login.success.total` - Counter with user.id attribute
- ✅ `users.login.failed.total` - Counter with reason attribute
- ✅ `articles.created.total` - Counter with user.id attribute
- ✅ `article.content.size` - Histogram with article.id attribute

**Metric Export Timing:**

- Metrics collected continuously during operations
- Exported every 60 seconds to OTel Collector
- Counters are cumulative (monotonic increasing)
- Gauges show current state
- Histograms show distribution over time

### Sensitive Data Protection

**Never appear in traces/logs:**

- ❌ Passwords (plaintext or hashed)
- ❌ JWT tokens
- ❌ Session IDs
- ❌ Full credit card numbers

**Properly masked:**

- ✅ `db.statement`: `{"email":"?"}` (not actual email value)
- ✅ `db.statement`: `{"password":"?"}` (placeholder)

### Resource Attributes (on all telemetry)

- ✅ `service.name: express-mongodb-app`
- ✅ `service.version: 1.0.0`
- ✅ `deployment.environment: development`

---

## Common Issues and Solutions

### Issue: No database traces

**Symptoms:** HTTP spans appear, but no mongodb.* spans

**Causes:**

- MongoDB instrumentation disabled in `telemetry.ts`
- Missing `--import` flag in Docker CMD

**Solution:** Verify `@opentelemetry/instrumentation-mongodb` is enabled and
app uses `--import ./dist/instrumentation.js`

---

### Issue: Logs missing trace_id

**Symptoms:** Logs appear but without `[trace_id=xxx]` prefix

**Causes:**

- Winston instrumentation not configured
- Logger not using OpenTelemetry context

**Solution:** Verify `WinstonInstrumentation` in instrumentations array and
`getTraceContext()` called in logger

---

### Issue: Span events not appearing

**Symptoms:** Expected span events (e.g., `auth_failed`) missing

**Causes:**

- `trace.getActiveSpan()` returns undefined
- Event added to wrong span

**Solution:** Verify OpenTelemetry context propagation and events added to
active span

---

### Issue: User attributes missing from HTTP span

**Symptoms:** Authenticated requests don't have `user.id` on HTTP span

**Causes:**

- Auth middleware not adding attributes to active span
- OpenTelemetry context not propagating

**Solution:** Check `currentSpan.setAttributes()` in auth middleware

---

## Testing Commands

### View Application Logs

```bash
docker logs express-mongodb-app 2>&1 | tail -50
```text

### View OTel Collector Output

```bash
docker logs otel-collector 2>&1 | tail -100
```text

### Find Trace by ID

```bash
docker logs otel-collector 2>&1 | grep "TRACE_ID"
```text

### Extract Span Hierarchy

```bash
docker logs otel-collector 2>&1 | \
  awk '/Trace ID       : TRACE_ID/,/^Span #[0-9]/ {print}' | \
  grep -E "(Span #|Name|Parent ID|ID   |Kind|Status)"
```text

### Get Log with Correlation

```bash
docker logs otel-collector 2>&1 | \
  grep -B 2 -A 10 "LOG_MESSAGE" | \
  grep -E "(Body:|Trace ID|Span ID|deployment.environment)"
```text

### View Metrics

**List All Available Metrics:**

```bash
docker logs otel-collector 2>&1 | \
  grep "Descriptor:" -A 3 | grep "Name:" | sort | uniq -c | sort -rn
```text

**Check Specific Metric:**

```bash
# Articles created counter
docker logs otel-collector 2>&1 | \
  grep -B 5 -A 15 "articles.created.total" | tail -30

# HTTP duration histogram
docker logs otel-collector 2>&1 | \
  grep -B 5 -A 20 "http.server.duration" | \
  grep -E "(Count:|Sum:|status_code)" | tail -20

# Article content size histogram
docker logs otel-collector 2>&1 | \
  grep -B 5 -A 15 "article.content.size" | \
  grep -E "(Count:|Sum:|Min:|Max:|article.id)"
```text

**Check Runtime Metrics:**

```bash
# Node.js event loop performance
docker logs otel-collector 2>&1 | \
  grep -A 10 "nodejs.eventloop.delay.p99"

# V8 heap memory usage
docker logs otel-collector 2>&1 | \
  grep -A 10 "v8js.memory.heap.used"

# Database connection pool
docker logs otel-collector 2>&1 | \
  grep -A 10 "db.client.connections.usage" | \
  grep -E "(state:|Value:)"
```text

---

## Quick Verification Script

Save this as `scripts/verify-telemetry.sh`:

```bash
#!/bin/bash

echo "Checking last 5 traces..."
docker logs otel-collector 2>&1 | grep "Trace ID       :" | tail -5

echo -e "\nChecking log correlation..."
docker logs express-mongodb-app 2>&1 | grep "trace_id=" | tail -5

echo -e "\nChecking for common issues..."
echo "✓ MongoDB spans present:"
docker logs otel-collector 2>&1 | grep -c "mongodb\." | head -1

echo "✓ HTTP spans present:"
docker logs otel-collector 2>&1 | grep -c "http.method" | head -1

echo "✓ Logs with trace_id:"
docker logs express-mongodb-app 2>&1 | \
  grep -c "trace_id=" | head -1

echo -e "\nChecking metrics..."
echo "✓ Custom application metrics:"
docker logs otel-collector 2>&1 | \
  grep -c "articles.created.total\|users.registered.total" | head -1

echo "✓ HTTP server metrics:"
docker logs otel-collector 2>&1 | \
  grep -c "http.server.duration" | head -1

echo "✓ Runtime metrics:"
docker logs otel-collector 2>&1 | \
  grep -c "nodejs.eventloop\|v8js.memory" | head -1

echo -e "\n✅ Basic telemetry verification complete!"
echo "Three signals present: Traces ✓ Logs ✓ Metrics ✓"
```text

---

## Expected Telemetry by Operation

### Trace Counts

| Operation | HTTP Spans | Controller Spans | DB Spans | Socket Spans |
|-----------|------------|------------------|----------|--------------|
| Health check | 1 | 0 | 2 (mongo+redis) | 0 |
| Validation error | 1 | 0 | 0-1 (auth only) | 0 |
| Registration | 1 | 1 | 2 (find+insert) | 0 |
| Login failed | 1 | 1 | 1 (find) | 0 |
| Login success | 1 | 1 | 1 (find) | 0 |
| Auth failure | 1 | 0 | 0 | 0 |
| Create article | 1 | 1 | 2 (auth+insert) | 2 |
| Invalid article ID | 1 | 1 (Error status) | 0 | 0 |
| List articles | 1 | 1 | 2 (aggregate+find) | 0 |
| Update without auth | 1 | 0 | 0 | 0 |
| Update with auth | 1 | 1 | 3 (auth+find+update) | 2 |
| Publish article (HTTP) | 1 | 1 | 2 (auth+find) | 0 |
| Publish (worker) | 0 (propagated) | 1 (job processor) | 2 (find+update) | 2 |
| Delete article | 1 | 1 | 3 (auth+find+delete) | 2 |

### Metrics Updates

| Operation | Counter Metrics | Histogram Metrics | Gauge Metrics |
|-----------|----------------|-------------------|---------------|
| Health check | - | `http.server.duration` | `db.client.connections.usage` |
| Validation error | - | `http.server.duration` (400) | - |
| Registration | `users.registered.total` +1 | `http.server.duration` (201) | `users.active.total` |
| Login failed | `users.login.failed.total` +1 | `http.server.duration` (401) | - |
| Login success | `users.login.success.total` +1 | `http.server.duration` (200) | - |
| Auth failure | - | `http.server.duration` (401) | - |
| Create article | `articles.created.total` +1 | `http.server.duration` (201), `article.content.size` | `articles.total` |
| Invalid article ID | - | `http.server.duration` (400) | - |
| List articles | - | `http.server.duration` (200) | `db.client.connections.usage` |
| Update without auth | - | `http.server.duration` (401) | - |
| Update with auth | - | `http.server.duration` (200) | `db.client.connections.usage` |
| Publish article (HTTP) | - | `http.server.duration` (200) | - |
| Publish article (worker) | `articles.published.total` +1 | `job.processing.duration` | `db.client.connections.usage` |
| Delete article | `articles.deleted.total` +1 | `http.server.duration` (204) | `articles.total` -1 |

### Log Entries

| Operation | Log Level | Components |
|-----------|-----------|------------|
| Health check | - | (no logs for success) |
| Validation error | WARN | error-handler |
| Registration | INFO | auth-controller |
| Login failed | WARN | auth-controller, error-handler |
| Login success | INFO | auth-controller |
| Auth failure | WARN | auth-middleware |
| Create article | INFO | socket-emitter |
| Invalid article ID | WARN | error-handler |
| List articles | - | (no logs for success) |
| Update without auth | WARN | auth-middleware |
| Update with auth | INFO | socket-emitter |
| Publish article (HTTP) | - | (no logs for job enqueue) |
| Publish article (worker) | INFO | socket-emitter |
| Delete article | INFO | socket-emitter |

---

## References

- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)
- [MongoDB Instrumentation](https://www.npmjs.com/package/@opentelemetry/instrumentation-mongodb)
- [Winston Instrumentation](https://www.npmjs.com/package/@opentelemetry/instrumentation-winston)
- [HTTP Instrumentation](https://www.npmjs.com/package/@opentelemetry/instrumentation-http)
