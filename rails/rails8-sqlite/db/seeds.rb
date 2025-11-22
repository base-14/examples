# This file should ensure the existence of records required to run the application in every environment (production,
# development, test). The code here should be idempotent so that it can be executed at any point in every environment.
# The data can then be loaded with the bin/rails db:seed command (or created alongside the database with db:setup).
#
# Example:
#
#   ["Action", "Comedy", "Drama", "Horror"].each do |genre_name|
#     MovieGenre.find_or_create_by!(name: genre_name)
# Clear existing data
Order.destroy_all
Food.destroy_all
Hotel.destroy_all
User.destroy_all

# Create sample user
user = User.create!(
  name: "John Doe",
  email: "john@example.com",
  password: "password"
)

# Create sample hotels
hotel1 = Hotel.create!(name: "Grand Palace Hotel")
hotel2 = Hotel.create!(name: "Seaside Resort")

# Create sample foods
Food.create!([
  {
    name: "Margherita Pizza",
    food_type: "Italian",
    category: "Main Course",
    price: 15.99,
    hotel: hotel1
  },
  {
    name: "Caesar Salad",
    food_type: "American",
    category: "Appetizer",
    price: 8.99,
    hotel: hotel1
  },
  {
    name: "Grilled Salmon",
    food_type: "Seafood",
    category: "Main Course",
    price: 24.99,
    hotel: hotel2
  },
  {
    name: "Chocolate Cake",
    food_type: "Dessert",
    category: "Dessert",
    price: 6.99,
    hotel: hotel2
  }
])
