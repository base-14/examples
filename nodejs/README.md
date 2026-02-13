# Node.js Examples

OpenTelemetry instrumentation examples for Node.js applications.

## Projects

| Project | Description |
| ------- | ----------- |
| [express5-postgres](./express5-postgres) | Express 5 + TypeScript + PostgreSQL 18 + BullMQ + Socket.io with background jobs and WebSocket support |
| [nestjs-postgres](./nestjs-postgres) | NestJS 11 + TypeScript + PostgreSQL 18 + BullMQ + Socket.io with enterprise architecture and background jobs |
| [nextjs-api-mongodb](./nextjs-api-mongodb) | Next.js 16 + TypeScript + MongoDB 8 + BullMQ with REST API routes and background jobs |
| [fastify-postgres](./fastify-postgres) | Fastify 5 + TypeScript + PostgreSQL 18 + Drizzle ORM + BullMQ with Pino structured logging |
| [express-typescript-mongodb](./express-typescript-mongodb) | Express + TypeScript + MongoDB with auto-instrumentation and Redis |

## Contributing

When adding new examples:

- Include a complete README with setup and usage instructions
- Provide docker-compose setup for easy local testing
- Include OpenTelemetry configuration (collector config recommended)
- Document all environment variables and endpoints
- Add troubleshooting section for common issues
- Keep examples focused and production-ready

Follow the structure of existing projects for consistency.
