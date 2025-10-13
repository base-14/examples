defmodule ChatApp.Chat do
  require Logger
  require OpenTelemetry.Tracer
  import Ecto.Query
  alias ChatApp.Repo
  alias ChatApp.Chat.Message

  def list_recent_messages(limit \\ 20) do
    Message
    |> order_by(desc: :inserted_at)
    |> limit(^limit)
    |> Repo.all()
    |> Enum.reverse()
  end

  def create_message(attrs \\ %{}) do
    OpenTelemetry.Tracer.with_span "chat.create_message" do
      # Add OTel trace context to logger metadata
      span_ctx = OpenTelemetry.Tracer.current_span_ctx()

      Logger.metadata(
        otel_trace_id: OpenTelemetry.Span.hex_trace_id(span_ctx),
        otel_span_id: OpenTelemetry.Span.hex_span_id(span_ctx)
      )

      result =
        %Message{}
        |> Message.changeset(attrs)
        |> Repo.insert()

      case result do
        {:ok, message} ->
          Logger.info("Message created successfully",
            message_id: message.id,
            user: message.name,
            user_id: message.user_id,
            content_length: String.length(message.content),
            user_type: if(message.user_id, do: "authenticated", else: "guest")
          )

          ChatApp.Telemetry.emit_message_sent(message)
          {:ok, message}

        {:error, changeset} ->
          Logger.warning("Message validation failed",
            errors: inspect(changeset.errors),
            params: inspect(changeset.params)
          )

          ChatApp.Telemetry.emit_message_validation_error(changeset.errors)
          {:error, changeset}
      end
    end
  end

  def change_message(%Message{} = message, attrs \\ %{}) do
    Message.changeset(message, attrs)
  end
end
