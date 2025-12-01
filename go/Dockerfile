# Build stage
FROM golang:1.25-alpine AS builder

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache git ca-certificates

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o parking-lot ./cmd/parking-lot

# Runtime stage
FROM alpine:latest

RUN apk --no-cache add ca-certificates wget

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/parking-lot .

# Expose port
EXPOSE 8080

# Run the application
ENTRYPOINT ["/app/parking-lot"]
CMD ["--mode=server", "--port=8080"]
