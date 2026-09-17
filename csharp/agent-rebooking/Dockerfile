FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src

COPY AgentRebooking.sln ./
COPY AgentRebooking/AgentRebooking.csproj AgentRebooking/

RUN dotnet restore AgentRebooking/AgentRebooking.csproj

COPY AgentRebooking/ AgentRebooking/

WORKDIR /src/AgentRebooking
RUN dotnet publish -c Release -o /app/publish /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

USER app

COPY --from=build --chown=app:app /app/publish .
# The LLM cost table, read by Llm/Pricing.cs for base14.gen_ai.cost. It has no entry
# for the Ollama model, so cost is zero on the default path. The approval gate does not
# read it: alternatives are priced from Postgres through BookingStorePriceLookup.
COPY --from=shared --chown=app:app pricing.json /app/pricing.json

EXPOSE 8080
ENV ASPNETCORE_HTTP_PORTS=8080
ENTRYPOINT ["dotnet", "AgentRebooking.dll"]
