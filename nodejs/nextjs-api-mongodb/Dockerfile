# Next.js 16 + MongoDB + OpenTelemetry Example
# Multi-stage Dockerfile | Jan 2026

# ==========================================================================
# Stage 1: Base
# ==========================================================================
FROM node:24-alpine AS base

# ==========================================================================
# Stage 2: Dependencies
# ==========================================================================
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# ==========================================================================
# Stage 3: Builder (Next.js app + Worker)
# ==========================================================================
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# Build Next.js app and worker
RUN npm run build && npm run build:worker

# ==========================================================================
# Stage 4: App Runner (Next.js standalone)
# ==========================================================================
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public

RUN mkdir .next
RUN chown nextjs:nodejs .next

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/api/health || exit 1

CMD ["node", "server.js"]

# ==========================================================================
# Stage 5: Worker Runner
# ==========================================================================
FROM base AS worker
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Install production dependencies only
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

# Copy bundled worker and instrumentation
COPY --from=builder /app/dist ./dist

RUN chown -R nextjs:nodejs /app

USER nextjs

CMD ["node", "--import", "./dist/instrumentation.js", "dist/worker.js"]
