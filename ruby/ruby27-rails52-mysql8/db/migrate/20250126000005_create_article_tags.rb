class CreateArticleTags < ActiveRecord::Migration[5.2]
  def change
    create_table :article_tags do |t|
      t.references :article, foreign_key: true, null: false, index: true
      t.references :tag, foreign_key: true, null: false, index: true

      t.timestamps

      t.index [:article_id, :tag_id], unique: true
    end
  end
end
