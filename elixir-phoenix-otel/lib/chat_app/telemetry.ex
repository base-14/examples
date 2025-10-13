defmodule ChatApp.Telemetry do
  require OpenTelemetry.Tracer

  def emit_message_sent(message) do
    :telemetry.execute(
      [:chat_app, :message, :sent],
      %{count: 1},
      %{
        user_type: if(message.user_id, do: "authenticated", else: "guest"),
        message_length: String.length(message.content)
      }
    )

    OpenTelemetry.Tracer.with_span "chat.message.sent" do
      span_ctx = OpenTelemetry.Tracer.current_span_ctx()

      OpenTelemetry.Span.set_attributes(span_ctx, [
        {"message.id", message.id},
        {"message.length", String.length(message.content)},
        {"user.type", if(message.user_id, do: "authenticated", else: "guest")},
        {"user.name", message.name}
      ])
    end
  end

  def emit_presence_update(user_count) do
    :telemetry.execute(
      [:chat_app, :presence, :update],
      %{user_count: user_count},
      %{}
    )
  end

  def emit_message_validation_error(errors) do
    :telemetry.execute(
      [:chat_app, :message, :validation_error],
      %{count: 1},
      %{errors: inspect(errors)}
    )
  end
end
