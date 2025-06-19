class Order < ApplicationRecord
  belongs_to :user
  belongs_to :food
  
  validates :quantity, presence: true, numericality: { greater_than: 0 }
  validates :total_price, presence: true, numericality: { greater_than: 0 }
  
  before_validation :calculate_total_price
  
  private
  
  def calculate_total_price
    self.total_price = food.price * quantity if food && quantity
  end
end
