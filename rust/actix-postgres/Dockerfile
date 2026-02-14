# Build stage
FROM rust:1.92-alpine AS builder

WORKDIR /app

RUN apk add --no-cache musl-dev openssl-dev pkgconfig

# Copy dependency files first for caching
COPY Cargo.toml Cargo.lock ./

# Create dummy source to build dependencies
RUN mkdir src && \
    echo "fn main() {}" > src/main.rs && \
    mkdir -p src/bin && \
    echo "fn main() {}" > src/bin/worker.rs && \
    echo "pub mod config; pub mod database; pub mod error; pub mod handlers; pub mod jobs; pub mod middleware; pub mod models; pub mod repository; pub mod routes; pub mod services; pub mod telemetry;" > src/lib.rs

# Build dependencies only
RUN cargo build --release 2>/dev/null || true

# Remove dummy source
RUN rm -rf src

# Copy actual source
COPY src ./src
COPY migrations ./migrations

# Build the actual application
RUN touch src/main.rs src/lib.rs && \
    cargo build --release --bin api

# Runtime stage
FROM alpine:3.21

WORKDIR /app

RUN apk add --no-cache ca-certificates tzdata wget && \
    adduser -D -g '' -u 1001 appuser

COPY --from=builder /app/target/release/api .
COPY --from=builder /app/migrations ./migrations

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:8080/api/health || exit 1

CMD ["./api"]
