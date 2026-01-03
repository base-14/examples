class CreateArticles < ActiveRecord::Migration[5.2]
  def change
    create_table :articles do |t|
      t.string :title, null: false, limit: 200
      t.string :slug, null: false, limit: 250
      t.text :description, null: false, limit: 1000
      t.text :body, null: false, limit: 65535
      t.references :author, foreign_key: { to_table: :users }, null: false, index: true
      t.integer :favorites_count, default: 0, null: false

      t.timestamps

      t.index :slug, unique: true
      t.index :created_at
      t.index :favorites_count
    end
  end
end
