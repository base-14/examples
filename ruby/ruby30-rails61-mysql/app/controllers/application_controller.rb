class ApplicationController < ActionController::API
  rescue_from ActiveRecord::RecordNotFound, with: :handle_not_found
  rescue_from ActiveRecord::RecordInvalid, with: :handle_unprocessable

  private

  def handle_not_found(exception)
    span = OpenTelemetry::Trace.current_span
    span.record_exception(exception)
    span.status = OpenTelemetry::Trace::Status.error(exception.message)

    trace_id = span.context.hex_trace_id
    span_id = span.context.hex_span_id
    Rails.logger.error "[trace_id=#{trace_id} span_id=#{span_id}] #{exception.class}: #{exception.message}"

    render json: { error: "Not found", trace_id: trace_id }, status: :not_found
  end

  def handle_unprocessable(exception)
    render json: { error: exception.message }, status: :unprocessable_entity
  end
end
