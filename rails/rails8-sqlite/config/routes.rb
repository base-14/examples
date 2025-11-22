Rails.application.routes.draw do
  # Health check route
  get "up" => "rails/health#show", as: :rails_health_check

  # Root route
  root "home#index"

  # Authentication routes
  get "/login", to: "sessions#new"
  post "/login", to: "sessions#create"
  delete "/logout", to: "sessions#destroy"

  # User routes
  get "/signup", to: "users#new"
  post "/signup", to: "users#create"
  get "/profile", to: "users#show"

  # Resource routes
  resources :hotels, only: [ :index, :show ]
  resources :orders, only: [ :index, :new, :create, :show ]

  # Food order routes
  get "/foods/:food_id/order", to: "orders#new", as: "new_food_order"
  post "/foods/:food_id/order", to: "orders#create"
end
