# Sample Rails application with OpenTelemetry instrumentation to send directly to Base14 OTLP collector with oidc

Steps to run the application:
1. Install the dependencies using `bundle install`.
2. Navigate to `config/initilizers/opentelemetry.rb`.
3. update the client-id, client-secret, token-url, endpoint.
4. Run the application using `rails server`
