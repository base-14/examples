# syntax = docker/dockerfile:1

# Base stage with dependencies
FROM ruby:2.7.7-slim AS base

# Install packages needed for deployment
RUN apt-get update -qq && \
  apt-get install -y --no-install-recommends \
  default-mysql-client \
  tzdata && \
  rm -rf /var/lib/apt/lists/*

WORKDIR /rails

# Set production environment
ENV RAILS_ENV="production" \
  BUNDLE_DEPLOYMENT="1" \
  BUNDLE_PATH="/usr/local/bundle" \
  BUNDLE_WITHOUT="development:test"

# Build stage for gems and assets
FROM base AS build

# Install packages needed to build gems
RUN apt-get update -qq && \
  apt-get install -y --no-install-recommends \
  build-essential \
  default-libmysqlclient-dev \
  git && \
  rm -rf /var/lib/apt/lists/*

# Install application gems
COPY Gemfile Gemfile.lock ./
RUN bundle install && \
  rm -rf ~/.bundle/ "${BUNDLE_PATH}"/ruby/*/cache "${BUNDLE_PATH}"/ruby/*/bundler/gems/*/.git

# Copy application code
COPY . .

# Final stage for app image
FROM base

# Copy built artifacts: gems and application
COPY --from=build /usr/local/bundle /usr/local/bundle
COPY --from=build /rails /rails

# Run and own only the runtime files as a non-root user for security
RUN groupadd -g 1000 rails && \
  useradd -u 1000 -g rails -s /bin/bash -m rails && \
  chown -R rails:rails db log storage tmp

USER rails:rails

# Entrypoint prepares the database.
ENTRYPOINT ["/rails/bin/docker-entrypoint"]

# Start the server by default, this can be overwritten at runtime
EXPOSE 3000
CMD ["./bin/rails", "server", "-b", "0.0.0.0"]
