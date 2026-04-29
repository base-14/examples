var builder = DistributedApplication.CreateBuilder(args);

var postgres = builder.AddPostgres("pg")
    .WithImageTag("18.3");

var articlesDb = postgres.AddDatabase("articles");

var collector = builder.AddContainer(
        "otel-collector",
        "otel/opentelemetry-collector-contrib",
        "0.151.0")
    .WithBindMount("../config/otel-collector.yaml", "/etc/otel-collector.yaml")
    .WithArgs("--config=/etc/otel-collector.yaml")
    .WithEnvironment("SCOUT_ENDPOINT", builder.Configuration["SCOUT_ENDPOINT"] ?? "")
    .WithEnvironment("SCOUT_CLIENT_ID", builder.Configuration["SCOUT_CLIENT_ID"] ?? "")
    .WithEnvironment("SCOUT_CLIENT_SECRET", builder.Configuration["SCOUT_CLIENT_SECRET"] ?? "")
    .WithEnvironment("SCOUT_TOKEN_URL", builder.Configuration["SCOUT_TOKEN_URL"] ?? "")
    .WithEnvironment("SCOUT_ENVIRONMENT", builder.Configuration["SCOUT_ENVIRONMENT"] ?? "development")
    .WithHttpEndpoint(port: 4317, targetPort: 4317, name: "grpc")
    .WithHttpEndpoint(port: 4318, targetPort: 4318, name: "http")
    .WithHttpEndpoint(port: 13133, targetPort: 13133, name: "health");

var collectorGrpcEndpoint = collector.GetEndpoint("grpc");

var notify = builder.AddProject<Projects.NotifySvc>("notify-svc")
    .WithHttpEndpoint(port: 8081, env: "ASPNETCORE_HTTP_PORTS")
    .WithEnvironment("OTEL_EXPORTER_OTLP_ENDPOINT", collectorGrpcEndpoint)
    .WithEnvironment("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    .WithEnvironment("OTEL_SERVICE_NAME", "notify-svc")
    .WaitFor(collector);

// OTLP routes to the local collector (not Aspire's dashboard receiver);
// the collector forwards to base14 Scout.
builder.AddProject<Projects.ArticlesApi>("articles-api")
    .WithHttpEndpoint(port: 8080, env: "ASPNETCORE_HTTP_PORTS")
    .WithReference(articlesDb)
    .WithEnvironment("Notify__BaseUrl", notify.GetEndpoint("http"))
    .WithEnvironment("OTEL_EXPORTER_OTLP_ENDPOINT", collectorGrpcEndpoint)
    .WithEnvironment("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    .WithEnvironment("OTEL_SERVICE_NAME", "articles-api")
    .WaitFor(postgres)
    .WaitFor(collector);

builder.Build().Run();
