# C# Examples

OpenTelemetry instrumentation examples for .NET applications.

## Projects

| Project | Description |
| ------- | ----------- |
| [dotnet-sqlserver](./dotnet-sqlserver) | .NET 9 ASP.NET Core + EF Core + Azure SQL Edge with Minimal APIs, rate limiting, and full OTel instrumentation |
| [aspire-postgres](./aspire-postgres) | .NET Aspire 13.2 + ASP.NET Core 9 + EF Core 9 + PostgreSQL 18 with ServiceDefaults pattern, custom ActivitySource and Meter, two-service distributed tracing, and parallel Aspire / Compose run modes |

## Contributing

When adding new examples:

- Include a complete README with setup and usage instructions
- Provide docker-compose setup for easy local testing
- Include OpenTelemetry configuration (collector config recommended)
- Document all environment variables and endpoints
- Add troubleshooting section for common issues
- Keep examples focused and production-ready

Follow the structure of existing projects for consistency.
