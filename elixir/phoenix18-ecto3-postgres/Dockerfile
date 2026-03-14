FROM elixir:1.18-slim

RUN apt-get update && apt-get install -y bash curl git build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN mix local.hex --force && mix local.rebar --force

COPY mix.exs mix.lock ./
RUN mix deps.get
RUN mix deps.compile

COPY . .
RUN mix compile

EXPOSE 4000
CMD ["mix", "phx.server"]
