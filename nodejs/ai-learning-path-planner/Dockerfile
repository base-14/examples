# AI Learning Path Planner
# Multi-stage build

FROM node:26.8.2-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts

FROM node:26.8.2-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:26.8.2-alpine AS runtime
WORKDIR /app

RUN apk add --no-cache curl

ENV NODE_ENV=production

COPY --from=deps /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package.json ./

# The corpus the store decompresses at boot. Without it the service throws before it
# listens, so the container never becomes healthy.
COPY --from=builder /app/data ./data

# src/llm/cost.ts resolves the price table four levels up from dist/llm/cost.js, which is
# /_shared/pricing.json inside this image. It comes from the `shared` named build context
# (see compose.yaml and the docker-build target) because the repo root is outside this
# build context.
COPY --from=shared pricing.json /_shared/pricing.json

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 planner && \
    chown -R planner:nodejs /app

USER planner

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1

# --import runs the telemetry module before the app's first import, which is what
# registers the ESM loader hook. Without it the container starts, answers requests and
# exports nothing at all, and every verification against it is meaningless.
CMD ["node", "--import", "./dist/telemetry.js", "dist/index.js"]
