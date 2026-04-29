FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build
WORKDIR /src

COPY AspirePostgres.sln ./
COPY ServiceDefaults/ServiceDefaults.csproj ServiceDefaults/
COPY ArticlesApi/ArticlesApi.csproj ArticlesApi/

RUN dotnet restore ArticlesApi/ArticlesApi.csproj

COPY ServiceDefaults/ ServiceDefaults/
COPY ArticlesApi/ ArticlesApi/

WORKDIR /src/ArticlesApi
RUN dotnet publish -c Release -o /app/publish /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:9.0 AS runtime
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

USER app

COPY --from=build --chown=app:app /app/publish .

EXPOSE 8080
ENV ASPNETCORE_HTTP_PORTS=8080
ENTRYPOINT ["dotnet", "ArticlesApi.dll"]
