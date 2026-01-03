class CreateComments < ActiveRecord::Migration[5.2]
  def change
    create_table :comments do |t|
      t.text :body, null: false, limit: 2000
      t.references :article, foreign_key: true, null: false, index: true
      t.references :author, foreign_key: { to_table: :users }, null: false, index: true

      t.timestamps

      t.index [:article_id, :created_at]
    end
  end
end
