FROM golang:1.25-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /app/inventory-worker ./services/inventory-worker/cmd

FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata

RUN adduser -D -g '' appuser

WORKDIR /app

COPY --from=builder /app/inventory-worker .

RUN chown -R appuser:appuser /app

USER appuser

CMD ["./inventory-worker"]
