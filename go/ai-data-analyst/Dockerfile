FROM golang:1.25.7-alpine AS builder

WORKDIR /build

RUN apk add --no-cache git ca-certificates

COPY _shared/ /build/_shared/
COPY go/ai-data-analyst/go.mod go/ai-data-analyst/go.sum /build/go/ai-data-analyst/
WORKDIR /build/go/ai-data-analyst
RUN go mod download

COPY go/ai-data-analyst/ /build/go/ai-data-analyst/
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /app/server ./cmd/server

FROM alpine:3.23

RUN apk --no-cache add ca-certificates wget

WORKDIR /app
COPY --from=builder /app/server .
COPY --from=builder /build/go/ai-data-analyst/data/schema-context.txt /app/data/schema-context.txt
COPY --from=builder /build/_shared/pricing.json /app/_shared/pricing.json

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8080/api/health || exit 1

ENTRYPOINT ["/app/server"]
