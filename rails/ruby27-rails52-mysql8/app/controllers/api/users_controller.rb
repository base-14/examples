module Api
  class UsersController < BaseController
    skip_before_action :authenticate_user, only: [:create, :login]
    before_action :authenticate_user, only: [:show, :update]

    # POST /api/register
    def create
      tracer.in_span('register_user') do |span|
        user = User.new(user_params)

        if user.save
          span.set_attribute('user.id', user.id)
          span.set_attribute('user.email', user.email)
          span.add_event('user_registered')

          render_success(
            user_response(user, include_token: true),
            { message: 'User registered successfully' },
            :created
          )
        else
          span.set_attribute('registration.failed', true)
          span.add_event('registration_validation_failed', attributes: {
            'errors' => user.errors.full_messages.join(', ')
          })
          render_validation_errors(user)
        end
      end
    end

    # POST /api/login
    def login
      tracer.in_span('user_login') do |span|
        user = User.find_by(email: login_params[:email]&.downcase)

        if user&.authenticate(login_params[:password])
          span.set_attribute('user.id', user.id)
          span.set_attribute('login.result', 'success')
          span.add_event('user_logged_in')

          render_success(
            user_response(user, include_token: true),
            { message: 'Login successful' }
          )
        else
          span.set_attribute('login.result', 'failed')
          span.add_event('login_failed', attributes: {
            'email' => login_params[:email]
          })
          render_error('invalid_credentials', 'Invalid email or password', :unauthorized)
        end
      end
    end

    # GET /api/user
    def show
      tracer.in_span('get_current_user') do |span|
        span.set_attribute('user.id', current_user.id)
        render_success(user_response(current_user, include_token: true))
      end
    end

    # PUT /api/user
    def update
      tracer.in_span('update_user') do |span|
        span.set_attribute('user.id', current_user.id)

        if current_user.update(update_user_params)
          span.add_event('user_updated')
          render_success(user_response(current_user, include_token: true))
        else
          span.add_event('user_update_failed')
          render_validation_errors(current_user)
        end
      end
    end

    private

    def user_params
      params.require(:user).permit(:email, :username, :password, :bio, :image_url)
    end

    def login_params
      params.require(:user).permit(:email, :password)
    end

    def update_user_params
      params.require(:user).permit(:email, :username, :password, :bio, :image_url)
    end

    def user_response(user, include_token: false)
      response = {
        id: user.id,
        email: user.email,
        username: user.username,
        bio: user.bio,
        image_url: user.image_url
      }
      response[:token] = user.generate_jwt if include_token
      response
    end
  end
end
