defmodule ChatApp.Chat.Message do
  use Ecto.Schema
  import Ecto.Changeset

  schema "messages" do
    field :content, :string
    field :name, :string
    field :user_id, :string
    field :avatar_url, :string

    timestamps(type: :utc_datetime)
  end

  @doc false
  def changeset(message, attrs) do
    message
    |> cast(attrs, [:content, :name, :user_id, :avatar_url])
    |> validate_required([:content, :name])
    |> validate_length(:content, min: 2, message: "must be at least 2 characters")
    |> validate_length(:name, min: 1)
  end
end
