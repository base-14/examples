# Elixir Hello World — OpenTelemetry (Traces Only)

defmodule HelloWorld do
  require OpenTelemetry.Tracer, as: Tracer

  # A normal operation — creates a span with an attribute and event.
  def say_hello do
    # A span represents a unit of work. Everything inside this block is part
    # of the "say-hello" span.
    Tracer.with_span "say-hello" do
      Tracer.set_attribute(:greeting, "Hello, World!")
      # Span events serve as log equivalents since the Elixir logs SDK is not yet stable.
      Tracer.add_event("greeting.sent", %{message: "Hello, World!"})
    end
  end

  # A degraded operation — creates a span with a warning event.
  def check_disk_space do
    Tracer.with_span "check-disk-space" do
      Tracer.set_attribute(:"disk.usage_percent", 92)
      # Span events are the closest equivalent to logs in traces-only mode.
      # They show up as annotations on the span in TraceX.
      Tracer.add_event("disk.warning", %{message: "Disk usage above 90%"})
    end
  end

  # A failed operation — creates a span with an error and exception.
  def parse_config do
    Tracer.with_span "parse-config" do
      try do
        raise "invalid config: missing 'database_url'"
      rescue
        e ->
          # record_exception attaches the stack trace to the span.
          # set_status marks the span as errored so it stands out in TraceX.
          Tracer.record_exception(e, __STACKTRACE__)
          Tracer.set_status(:error, Exception.message(e))
      end
    end
  end
end
