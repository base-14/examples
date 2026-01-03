Rails.application.routes.draw do
  namespace :api do
    # Health check
    get 'health', to: 'health#show'

    # Background jobs
    post 'jobs', to: 'jobs#create'
    post 'jobs/bulk_process', to: 'jobs#bulk_process'

    # Metrics
    get 'metrics', to: 'metrics#index'

    # Authentication
    post 'register', to: 'users#create'
    post 'login', to: 'users#login'
    get 'user', to: 'users#show'
    put 'user', to: 'users#update'

    # Articles
    resources :articles, param: :slug do
      # Favorites
      post 'favorite', to: 'favorites#create', on: :member
      delete 'favorite', to: 'favorites#destroy', on: :member

      # Comments
      resources :comments, only: [:index, :create, :destroy]
    end

    # Tags
    resources :tags, only: [:index]
  end
end
