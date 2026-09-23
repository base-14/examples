FROM mcr.microsoft.com/dotnet/sdk:8.0.416 AS build
WORKDIR /src

COPY HelloSqlServer.csproj global.json ./
RUN dotnet restore

COPY . .
ARG TARGETARCH
RUN case "$TARGETARCH" in \
      amd64) RID=linux-x64 ;; \
      arm64) RID=linux-arm64 ;; \
      *) echo "unsupported TARGETARCH: $TARGETARCH" && exit 1 ;; \
    esac \
    && dotnet publish -c Release -r "$RID" --self-contained false -o /app/publish /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:8.0.22 AS runtime
WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY --from=build /app/publish .
RUN chmod +x instrument.sh

EXPOSE 8080
ENTRYPOINT ["./instrument.sh", "dotnet", "HelloSqlServer.dll"]
