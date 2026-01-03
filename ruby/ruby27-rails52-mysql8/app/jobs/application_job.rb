class ApplicationJob
  include Sidekiq::Job

  def tracer
    @tracer ||= OpenTelemetryHelper.tracer
  end
end
