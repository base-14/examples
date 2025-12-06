# Build stage
FROM node:24-alpine AS builder

WORKDIR /app

RUN apk add --no-cache python3 make g++

COPY package*.json tsconfig.json ./

RUN npm install

COPY src ./src

RUN npm run build

RUN npm prune --production

# Runtime stage
FROM node:24-alpine

WORKDIR /app

RUN apk add --no-cache curl

RUN addgroup -S appuser && \
    adduser -D -S -G appuser appuser

COPY --from=builder --chown=appuser:appuser /app/dist ./dist
COPY --from=builder --chown=appuser:appuser /app/node_modules ./node_modules
COPY --chown=appuser:appuser package*.json ./

USER appuser

EXPOSE 3000

HEALTHCHECK --interval=5m --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:3000/api/health || exit 1

CMD ["node", "--import", "./dist/instrumentation.js", "dist/index.js"]
