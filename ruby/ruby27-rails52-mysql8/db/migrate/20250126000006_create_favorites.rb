class CreateFavorites < ActiveRecord::Migration[5.2]
  def change
    create_table :favorites do |t|
      t.references :user, foreign_key: true, null: false, index: true
      t.references :article, foreign_key: true, null: false, index: true

      t.timestamps

      t.index [:user_id, :article_id], unique: true
      t.index :created_at
    end
  end
end
