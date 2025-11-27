module Authenticatable
  extend ActiveSupport::Concern

  included do
    before_action :authenticate_user, except: [:index, :show]
    attr_reader :current_user
  end

  private

  def authenticate_user
    tracer.in_span('authenticate_user') do |span|
      token = extract_token_from_header

      if token.blank?
        span.set_attribute('auth.result', 'no_token')
        render_unauthorized('Missing authentication token')
        return
      end

      decoded_token = JwtConfig.decode(token)

      if decoded_token.nil?
        span.set_attribute('auth.result', 'invalid_token')
        render_unauthorized('Invalid or expired token')
        return
      end

      @current_user = User.find_by(id: decoded_token['user_id'])

      if @current_user.nil?
        span.set_attribute('auth.result', 'user_not_found')
        render_unauthorized('User not found')
        return
      end

      span.set_attribute('auth.result', 'success')
      span.set_attribute('user.id', @current_user.id)
      span.set_attribute('user.email', @current_user.email)
    end
  rescue => e
    tracer.in_span('authentication_error') do |span|
      span.record_exception(e)
      span.status = OpenTelemetry::Trace::Status.error("Authentication failed: #{e.message}")
    end
    render_unauthorized('Authentication failed')
  end

  def authenticate_user!
    authenticate_user
  end

  def optional_authentication
    token = extract_token_from_header
    return unless token.present?

    decoded_token = JwtConfig.decode(token)
    @current_user = User.find_by(id: decoded_token['user_id']) if decoded_token
  end

  def extract_token_from_header
    header = request.headers['Authorization']
    return nil if header.blank?

    # Support both "Token xxx" and "Bearer xxx" formats
    header.split(' ').last if header.match(/^(Token|Bearer) /)
  end

  def render_unauthorized(message = 'Unauthorized')
    render_error('unauthorized', message, :unauthorized)
  end
end
