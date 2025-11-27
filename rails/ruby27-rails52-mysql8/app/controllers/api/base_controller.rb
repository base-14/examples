module Api
  class BaseController < ActionController::API
    include ApiResponse
    include Authenticatable

    rescue_from ActiveRecord::RecordNotFound, with: :handle_not_found
    rescue_from ActiveRecord::RecordInvalid, with: :handle_invalid_record
    rescue_from ActionController::ParameterMissing, with: :handle_parameter_missing

    # OpenTelemetry helper for custom instrumentation
    def tracer
      @tracer ||= OpenTelemetryHelper.tracer
    end

    # Add trace attributes for current request
    def add_trace_attributes(attributes = {})
      span = OpenTelemetry::Trace.current_span
      attributes.each do |key, value|
        span.set_attribute(key.to_s, value.to_s)
      end
    end

    # Record an event in the current span
    def record_trace_event(name, attributes = {})
      span = OpenTelemetry::Trace.current_span
      span.add_event(name, attributes: attributes)
    end

    private

    def handle_not_found(exception)
      render_error('not_found', exception.message, :not_found)
    end

    def handle_invalid_record(exception)
      render_error('invalid_record', exception.message, :unprocessable_entity)
    end

    def handle_parameter_missing(exception)
      render_error('parameter_missing', exception.message, :bad_request)
    end
  end
end
