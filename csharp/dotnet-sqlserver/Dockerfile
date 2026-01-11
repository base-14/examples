# Build stage
FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build
WORKDIR /src

# Copy solution and project files
COPY DotnetSqlServer.sln .
COPY src/Api/Api.csproj src/Api/
COPY src/Worker/Worker.csproj src/Worker/

# Restore dependencies
RUN dotnet restore src/Api/Api.csproj

# Copy source code
COPY src/Api/ src/Api/

# Build and publish
WORKDIR /src/src/Api
RUN dotnet publish -c Release -o /app/publish /p:UseAppHost=false

# Runtime stage
FROM mcr.microsoft.com/dotnet/aspnet:9.0 AS runtime
WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy published output
COPY --from=build /app/publish .

EXPOSE 8080
ENTRYPOINT ["dotnet", "Api.dll"]
