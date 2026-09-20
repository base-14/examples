FROM oven/bun:1.3.9-alpine AS deps
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile --production

FROM oven/bun:1.3.9-alpine AS runtime
WORKDIR /app

RUN apk add --no-cache curl && \
    addgroup --system --gid 1001 analyzer && \
    adduser --system --uid 1001 --ingroup analyzer analyzer

COPY --from=deps --chown=analyzer:analyzer /app/node_modules ./node_modules
COPY --chown=analyzer:analyzer package.json tsconfig.json ./
COPY --chown=analyzer:analyzer src ./src

# src/llm/pricing.ts resolves the price table four levels up from
# /app/src/llm/pricing.ts, which is /_shared/pricing.json in this image. It comes
# from the `shared` named build context because the repo root is outside the
# build context (see compose.yaml and the docker-build target).
COPY --from=shared --chown=analyzer:analyzer pricing.json /_shared/pricing.json

ENV NODE_ENV=production

USER analyzer

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1

CMD ["bun", "run", "--preload", "./src/telemetry.ts", "src/index.ts"]
