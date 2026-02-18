ARG RUBY_VERSION=3.0
FROM docker.io/library/ruby:$RUBY_VERSION-slim

WORKDIR /rails

RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y \
      build-essential \
      default-libmysqlclient-dev \
      curl \
      git \
      libyaml-dev \
      pkg-config && \
    rm -rf /var/lib/apt/lists /var/cache/apt/archives

ENV RAILS_ENV="development" \
    BUNDLE_PATH="/usr/local/bundle"

RUN gem update --system 3.3.27 && gem install bundler -v 2.3.27

COPY Gemfile ./
RUN bundle install && \
    rm -rf ~/.bundle/ "${BUNDLE_PATH}"/ruby/*/cache "${BUNDLE_PATH}"/ruby/*/bundler/gems/*/.git

COPY . .

EXPOSE 3000

CMD ["bash", "-c", "bin/rails db:create 2>&1 || true; bin/rails db:migrate && bin/rails server -b 0.0.0.0 -p 3000"]
