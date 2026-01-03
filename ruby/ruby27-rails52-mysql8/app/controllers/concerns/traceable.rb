require 'securerandom'

module Traceable
  extend ActiveSupport::Concern

  included do
    around_action :trace_request
  end

  private

  def trace_request
    trace_id = SecureRandom.hex(16)
    span_id = SecureRandom.hex(8)

    start_time = Time.current
    status_code = 1

    begin
      yield
    rescue => e
      status_code = 2
      raise
    ensure
      end_time = Time.current

      trace_data = {
        trace_id: trace_id,
        spans: [
          {
            span_id: span_id,
            parent_span_id: nil,
            name: "#{request.method} #{request.path}",
            kind: :server,
            start_time: start_time,
            end_time: end_time,
            status_code: status_code,
            attributes: {
              'http.method' => request.method,
              'http.target' => request.path,
              'http.route' => "#{controller_name}##{action_name}",
              'http.status_code' => response.status,
              'http.user_agent' => request.user_agent,
              'net.host.name' => request.host,
              'net.host.port' => request.port
            }
          }
        ]
      }

      export_trace(trace_data)
    end
  end

  def export_trace(trace_data)
    OtlpExporter.new.export_trace(trace_data)
  end

  def with_span(name, attributes: {}, kind: :internal)
    span_id = SecureRandom.hex(8)
    start_time = Time.current
    status_code = 1

    begin
      yield
    rescue => e
      status_code = 2
      raise
    ensure
      end_time = Time.current

      span_data = {
        span_id: span_id,
        parent_span_id: Thread.current[:current_span_id],
        name: name,
        kind: kind,
        start_time: start_time,
        end_time: end_time,
        status_code: status_code,
        attributes: attributes
      }

      Thread.current[:spans] ||= []
      Thread.current[:spans] << span_data
    end
  end
end
