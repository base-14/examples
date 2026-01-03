module OpentelemetryTracing
  extend ActiveSupport::Concern

  included do
    around_action :trace_controller_action
  end

  private

  def trace_controller_action
    tracer = OpenTelemetryHelper.tracer

    tracer.in_span(
      "#{controller_name}##{action_name}",
      attributes: base_trace_attributes,
      kind: :server
    ) do |span|
      # Execute the controller action
      yield

      # Add response attributes after action completes
      add_response_attributes(span)
    end
  rescue => e
    # Record exception in span
    span = OpenTelemetry::Trace.current_span
    span.record_exception(e)
    span.status = OpenTelemetry::Trace::Status.error("Unhandled exception: #{e.class.name}")
    raise
  end

  def base_trace_attributes
    {
      'http.method' => request.method,
      'http.url' => request.original_url,
      'http.path' => request.path,
      'http.route' => "#{controller_path}##{action_name}",
      'http.user_agent' => request.user_agent,
      'http.request_id' => request.request_id,
      'controller.name' => controller_name,
      'controller.action' => action_name,
      'controller.class' => self.class.name,
      'rails.route_params' => sanitized_params.to_json
    }.tap do |attrs|
      # Add query parameters if present
      attrs['http.query_string'] = request.query_string if request.query_string.present?

      # Add client IP
      attrs['http.client_ip'] = request.remote_ip if request.remote_ip

      # Add format if present
      attrs['http.format'] = request.format.to_s if request.format
    end
  end

  def add_response_attributes(span)
    span.set_attribute('http.status_code', response.status)
    span.set_attribute('http.response_content_type', response.content_type) if response.content_type

    # Set span status based on HTTP status code
    if response.status >= 500
      span.status = OpenTelemetry::Trace::Status.error("HTTP #{response.status}")
    elsif response.status >= 400
      span.status = OpenTelemetry::Trace::Status.error("Client error: HTTP #{response.status}")
    else
      span.status = OpenTelemetry::Trace::Status.ok
    end
  end

  def sanitized_params
    # Remove sensitive parameters
    params.to_unsafe_h.except('controller', 'action', 'password', 'password_confirmation', 'token', 'secret')
  end
end
