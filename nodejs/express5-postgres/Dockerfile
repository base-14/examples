# Express 5 + PostgreSQL + OpenTelemetry Example
# Multi-stage Dockerfile | Dec 2025

# ==========================================================================
# Stage 1: Builder
# ==========================================================================
FROM node:24-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci

# Copy source and build
COPY tsconfig.json ./
COPY drizzle.config.ts ./
COPY src ./src

RUN npm run build

# ==========================================================================
# Stage 2: Runtime
# ==========================================================================
FROM node:24-alpine AS runtime

WORKDIR /app

# Create non-root user
RUN addgroup -g 1001 -S appgroup && \
    adduser -S appuser -u 1001 -G appgroup

# Install production dependencies only
COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

# Copy built application
COPY --from=builder /app/dist ./dist

# Copy drizzle migrations from build context
COPY drizzle ./drizzle

# Set ownership
RUN chown -R appuser:appgroup /app

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8000/api/health || exit 1

EXPOSE 8000

CMD ["node", "dist/index.js"]
