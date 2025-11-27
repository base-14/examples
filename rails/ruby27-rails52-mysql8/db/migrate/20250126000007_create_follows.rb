class CreateFollows < ActiveRecord::Migration[5.2]
  def change
    create_table :follows do |t|
      t.bigint :follower_id, null: false
      t.bigint :followee_id, null: false

      t.timestamps

      t.index :follower_id
      t.index :followee_id
      t.index [:follower_id, :followee_id], unique: true
    end

    add_foreign_key :follows, :users, column: :follower_id
    add_foreign_key :follows, :users, column: :followee_id
  end
end
