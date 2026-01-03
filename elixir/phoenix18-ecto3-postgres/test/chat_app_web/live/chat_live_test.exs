defmodule ChatAppWeb.ChatLiveTest do
  use ChatAppWeb.ConnCase
  import Phoenix.LiveViewTest
  alias ChatApp.Chat

  describe "ChatLive" do
    test "renders the chat interface", %{conn: conn} do
      {:ok, _view, html} = live(conn, "/")
      assert html =~ "LiveView Chat"
      assert html =~ "Type a message"
    end

    test "displays existing messages", %{conn: conn} do
      {:ok, _message} = Chat.create_message(%{content: "Test message", name: "Alice"})
      {:ok, _view, html} = live(conn, "/")
      assert html =~ "Test message"
      assert html =~ "Alice"
    end

    test "sends a new message", %{conn: conn} do
      {:ok, view, _html} = live(conn, "/")

      view
      |> form("#message-form", message: %{content: "Hello from test", name: "TestUser"})
      |> render_submit()

      assert render(view) =~ "Hello from test"
      assert render(view) =~ "TestUser"
    end

    test "validates message content length", %{conn: conn} do
      {:ok, view, _html} = live(conn, "/")

      html =
        view
        |> form("#message-form", message: %{content: "x", name: "TestUser"})
        |> render_submit()

      assert html =~ "must be at least 2 characters"
    end

    test "requires name field", %{conn: conn} do
      {:ok, view, _html} = live(conn, "/")

      html =
        view
        |> form("#message-form", message: %{content: "Hello world", name: ""})
        |> render_submit()

      assert html =~ "can&#39;t be blank"
    end

    test "displays user count", %{conn: conn} do
      {:ok, _view, html} = live(conn, "/")
      assert html =~ "online"
    end

    test "new messages appear in real-time", %{conn: conn} do
      {:ok, view, _html} = live(conn, "/")

      {:ok, message} = Chat.create_message(%{content: "Broadcast test", name: "Bob"})
      send(view.pid, {:new_message, message})

      assert render(view) =~ "Broadcast test"
      assert render(view) =~ "Bob"
    end
  end
end
