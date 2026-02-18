Rails.application.routes.draw do
  get "/api/health", to: "health#show"
  post "/api/items", to: "items#create"
  get "/api/items/:id", to: "items#show"
end
