defmodule ChatAppWeb.Presence do
  use Phoenix.Presence,
    otp_app: :chat_app,
    pubsub_server: ChatApp.PubSub
end
