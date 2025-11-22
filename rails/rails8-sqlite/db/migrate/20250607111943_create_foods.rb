class CreateFoods < ActiveRecord::Migration[8.0]
  def change
    create_table :foods do |t|
      t.string :name
      t.string :food_type
      t.string :category
      t.decimal :price
      t.references :hotel, null: false, foreign_key: true

      t.timestamps
    end
  end
end
