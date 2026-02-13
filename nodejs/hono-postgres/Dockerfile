# Hono + PostgreSQL + OpenTelemetry Example
# Multi-stage build for optimized production image | Feb 2026

# =============================================================================
# Stage 1: Dependencies
# =============================================================================
FROM node:24.13.1-alpine3.23 AS deps

WORKDIR /app

COPY package.json package-lock.json* ./

RUN npm ci --ignore-scripts

# =============================================================================
# Stage 2: Builder
# =============================================================================
FROM node:24.13.1-alpine3.23 AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build

# =============================================================================
# Stage 3: Runtime
# =============================================================================
FROM node:24.13.1-alpine3.23 AS runtime

WORKDIR /app

RUN apk add --no-cache curl gcompat

ENV NODE_ENV=production

COPY --from=deps /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package.json ./
COPY --from=builder /app/drizzle ./drizzle

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 hono && \
    chown -R hono:nodejs /app

USER hono

EXPOSE 3000

CMD ["node", "dist/index.js"]
