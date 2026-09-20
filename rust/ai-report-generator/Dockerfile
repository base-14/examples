FROM rust:1.98-alpine AS builder

WORKDIR /build

RUN apk add --no-cache musl-dev openssl-dev openssl-libs-static pkgconfig protobuf-dev

COPY _shared/ /build/_shared/
COPY rust/ai-report-generator/Cargo.toml rust/ai-report-generator/Cargo.lock /build/rust/ai-report-generator/

WORKDIR /build/rust/ai-report-generator

RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo build --release 2>/dev/null || true
RUN rm -rf src

COPY rust/ai-report-generator/src ./src
COPY rust/ai-report-generator/data ./data

RUN touch src/main.rs && cargo build --release --bin server

FROM alpine:3.23

RUN apk add --no-cache ca-certificates tzdata wget && \
    adduser -D -g '' -u 1001 appuser

WORKDIR /app

COPY --from=builder /build/rust/ai-report-generator/target/release/server .

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -q --spider http://localhost:8080/api/health || exit 1

CMD ["./server"]
