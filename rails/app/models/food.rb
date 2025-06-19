class Food < ApplicationRecord
  belongs_to :hotel

  validates :name, presence: true
  validates :food_type, presence: true
  validates :category, presence: true
  validates :price, presence: true, numericality: { greater_than: 0 }

  has_many :orders, dependent: :destroy
end
