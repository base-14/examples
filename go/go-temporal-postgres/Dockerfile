FROM golang:1.25.7-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /app/api ./cmd/api

FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata wget

RUN adduser -D -g '' appuser

WORKDIR /app

COPY --from=builder /app/api .

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:8080/api/health || exit 1

CMD ["./api"]
