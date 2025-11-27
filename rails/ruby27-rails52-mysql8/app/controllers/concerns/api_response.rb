module ApiResponse
  extend ActiveSupport::Concern

  def render_success(data, meta = {}, status = :ok)
    tracer.in_span('render_success') do |span|
      response_meta = build_meta(meta)

      span.set_attribute('response.status', 'success')
      span.set_attribute('response.http_status', Rack::Utils::SYMBOL_TO_STATUS_CODE[status])

      render json: {
        data: data,
        meta: response_meta
      }, status: status
    end
  end

  def render_error(code, message, status = :bad_request, details = {})
    tracer.in_span('render_error') do |span|
      response_meta = build_meta

      span.set_attribute('response.status', 'error')
      span.set_attribute('response.error_code', code)
      span.set_attribute('response.http_status', Rack::Utils::SYMBOL_TO_STATUS_CODE[status])
      span.add_event('error_response', attributes: { 'error.message' => message })

      error_payload = {
        error: {
          code: code,
          message: message
        },
        meta: response_meta
      }

      error_payload[:error][:details] = details if details.present?

      render json: error_payload, status: status
    end
  end

  def render_validation_errors(model)
    render_error(
      'validation_failed',
      'Validation failed',
      :unprocessable_entity,
      model.errors.messages
    )
  end

  private

  def build_meta(additional_meta = {})
    span = OpenTelemetry::Trace.current_span
    trace_id = span.context.trace_id.unpack1('H*')

    {
      trace_id: trace_id,
      request_id: request.request_id,
      timestamp: Time.current.iso8601
    }.merge(additional_meta)
  end
end
