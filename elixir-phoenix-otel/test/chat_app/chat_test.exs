defmodule ChatApp.ChatTest do
  use ChatApp.DataCase

  alias ChatApp.Chat
  alias ChatApp.Chat.Message

  describe "messages" do
    @valid_attrs %{content: "Hello world", name: "Alice", user_id: nil, avatar_url: nil}

    test "list_recent_messages/0 returns all messages" do
      {:ok, message} = Chat.create_message(@valid_attrs)
      messages = Chat.list_recent_messages()
      assert length(messages) == 1
      assert hd(messages).id == message.id
    end

    test "list_recent_messages/1 limits the number of messages returned" do
      for i <- 1..25 do
        Chat.create_message(Map.put(@valid_attrs, :content, "Message #{i}"))
      end

      messages = Chat.list_recent_messages(10)
      assert length(messages) == 10
    end

    test "create_message/1 with valid data creates a message" do
      assert {:ok, %Message{} = message} = Chat.create_message(@valid_attrs)
      assert message.content == "Hello world"
      assert message.name == "Alice"
      assert message.user_id == nil
      assert message.avatar_url == nil
    end

    test "create_message/1 with authenticated user" do
      attrs = %{
        content: "Hello",
        name: "Bob",
        user_id: "user123",
        avatar_url: "https://example.com/avatar.png"
      }

      assert {:ok, %Message{} = message} = Chat.create_message(attrs)
      assert message.user_id == "user123"
      assert message.avatar_url == "https://example.com/avatar.png"
    end

    test "create_message/1 with content less than 2 characters returns error changeset" do
      attrs = %{content: "x", name: "Alice"}
      assert {:error, %Ecto.Changeset{}} = Chat.create_message(attrs)
    end

    test "create_message/1 without content returns error changeset" do
      attrs = %{content: "", name: "Alice"}
      assert {:error, %Ecto.Changeset{}} = Chat.create_message(attrs)
    end

    test "create_message/1 without name returns error changeset" do
      attrs = %{content: "Hello world", name: ""}
      assert {:error, %Ecto.Changeset{}} = Chat.create_message(attrs)
    end

    test "change_message/1 returns a message changeset" do
      {:ok, message} = Chat.create_message(@valid_attrs)
      assert %Ecto.Changeset{} = Chat.change_message(message)
    end
  end
end
