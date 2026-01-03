defmodule ChatAppWeb.ChatLive do
  use ChatAppWeb, :live_view
  require Logger
  alias ChatApp.Chat
  alias ChatApp.Chat.Message
  alias Phoenix.PubSub

  @topic "liveview_chat"

  def mount(_params, _session, socket) do
    if connected?(socket) do
      Logger.info("User connected to chat", socket_id: socket.id)
      PubSub.subscribe(ChatApp.PubSub, @topic)

      ChatAppWeb.Presence.track(self(), @topic, socket.id, %{
        name: "Guest",
        joined_at: System.system_time(:second)
      })
    end

    messages = Chat.list_recent_messages()
    form = Chat.change_message(%Message{}) |> to_form()

    Logger.debug("Chat LiveView mounted",
      socket_id: socket.id,
      connected: connected?(socket),
      message_count: length(messages)
    )

    {:ok,
     socket
     |> assign(:messages, messages)
     |> assign(:form, form)
     |> assign(:name, "")
     |> assign(:users, %{})
     |> stream_configure(:messages, dom_id: &"message-#{&1.id}")
     |> stream(:messages, messages, at: -1), temporary_assigns: [messages: []]}
  end

  def handle_event("send_message", %{"message" => message_params}, socket) do
    name = if socket.assigns.name != "", do: socket.assigns.name, else: message_params["name"]

    attrs = %{
      content: message_params["content"],
      name: name,
      user_id: nil,
      avatar_url: nil
    }

    case Chat.create_message(attrs) do
      {:ok, message} ->
        Logger.info("Broadcasting message to chat",
          message_id: message.id,
          topic: @topic
        )

        PubSub.broadcast(ChatApp.PubSub, @topic, {:new_message, message})

        {:noreply,
         socket
         |> assign(:form, Chat.change_message(%Message{}) |> to_form())
         |> assign(:name, name)
         |> push_event("clear-input", %{})}

      {:error, changeset} ->
        Logger.debug("Message send failed, showing validation errors")
        {:noreply, assign(socket, :form, to_form(changeset))}
    end
  end

  def handle_info({:new_message, message}, socket) do
    {:noreply, stream_insert(socket, :messages, message, at: -1)}
  end

  def handle_info(%{event: "presence_diff", payload: diff}, socket) do
    users =
      socket.assigns.users
      |> remove_presences(diff.leaves)
      |> add_presences(diff.joins)

    Logger.info("Presence updated",
      total_users: map_size(users),
      joins: map_size(diff.joins),
      leaves: map_size(diff.leaves)
    )

    ChatApp.Telemetry.emit_presence_update(map_size(users))

    {:noreply, assign(socket, :users, users)}
  end

  defp add_presences(users, joins) do
    Enum.reduce(joins, users, fn {id, %{metas: [meta | _]}}, acc ->
      Map.put(acc, id, meta)
    end)
  end

  defp remove_presences(users, leaves) do
    Enum.reduce(leaves, users, fn {id, _}, acc ->
      Map.delete(acc, id)
    end)
  end

  defp format_timestamp(datetime) do
    Calendar.strftime(datetime, "%H:%M")
  end
end
