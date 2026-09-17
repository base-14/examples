# Node.js Examples

OpenTelemetry instrumentation examples for Node.js applications. Part of base14's
[OpenTelemetry examples](../README.md) repository; the docs live at
[docs.base14.io](https://docs.base14.io/instrument/apps/auto-instrumentation/nodejs/).

## Projects

| Project | Description |
| ------- | ----------- |
| [express5-postgres](./express5-postgres) | Express 5 + TypeScript + PostgreSQL 18 + BullMQ + Socket.io with background jobs and WebSocket support |
| [nestjs-postgres](./nestjs-postgres) | NestJS 11 + TypeScript + PostgreSQL 18 + BullMQ + Socket.io with enterprise architecture and background jobs |
| [nextjs-api-mongodb](./nextjs-api-mongodb) | Next.js 16 + TypeScript + MongoDB 8 + BullMQ with REST API routes and background jobs |
| [nextjs-fullstack-otel](./nextjs-fullstack-otel) | Next.js 16 + Full-stack OTel (server + browser) with error capture, web vitals, and console bridge |
| [angular-fullstack-otel](./angular-fullstack-otel) | Angular 22 (zoneless) SPA + Express 5 + PostgreSQL 18 with browser OTel (traces, metrics, logs), Core Web Vitals, and W3C trace propagation from the browser through the API to Postgres |
| [fastify-postgres](./fastify-postgres) | Fastify 5 + TypeScript + PostgreSQL 18 + Drizzle ORM + BullMQ with Pino structured logging |
| [trpc-postgres](./trpc-postgres) | tRPC 11 + TypeScript 6 + Prisma 7 + PostgreSQL 18 with OTel Node SDK and distributed tracing |
| [express-typescript-mongodb](./express-typescript-mongodb) | Express + TypeScript + MongoDB with auto-instrumentation and Redis |
| [ai-learning-path-planner](./ai-learning-path-planner) | Node.js 26 + Hono 4 + Vercel AI SDK 7 + local Ollama models, a lead agent fanning out to one researcher subagent per subtopic over base14's own docs and examples corpus, with per-run cost and tool-definition token metrics. Guide: [AI Agent Observability](https://docs.base14.io/guides/ai-observability/agent-observability/) |

## Contributing

When adding new examples:

- Include a complete README with setup and usage instructions
- Provide docker-compose setup for easy local testing
- Include OpenTelemetry configuration (collector config recommended)
- Document all environment variables and endpoints
- Add troubleshooting section for common issues
- Keep examples focused and production-ready

Follow the structure of existing projects for consistency.
