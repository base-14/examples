FROM oven/bun:1.2-alpine AS base
WORKDIR /app

FROM base AS deps
COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile --production

FROM base AS dev
COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile

FROM base AS production
COPY --from=deps /app/node_modules ./node_modules
COPY src ./src
COPY tsconfig.json ./

ENV NODE_ENV=production

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1

CMD ["bun", "run", "src/index.ts"]
