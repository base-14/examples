defmodule ChatApp.Repo.Migrations.CreateMessages do
  use Ecto.Migration

  def change do
    create table(:messages) do
      add :content, :string, null: false
      add :name, :string, null: false
      add :user_id, :string
      add :avatar_url, :string

      timestamps(type: :utc_datetime)
    end

    create index(:messages, [:inserted_at])
  end
end
