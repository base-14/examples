class CreateUsers < ActiveRecord::Migration[5.2]
  def change
    create_table :users do |t|
      t.string :email, null: false, limit: 255
      t.string :username, null: false, limit: 50
      t.string :password_digest, null: false
      t.string :bio, limit: 500
      t.string :image_url, limit: 500

      t.timestamps

      t.index :email, unique: true
      t.index :username, unique: true
    end
  end
end
