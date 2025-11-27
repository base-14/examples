module JwtConfig
  SECRET_KEY = Rails.application.credentials.secret_key_base || ENV['SECRET_KEY_BASE']
  ALGORITHM = 'HS256'
  EXPIRATION = 24.hours.to_i

  def self.encode(payload, exp = nil)
    exp ||= Time.now.to_i + EXPIRATION
    payload[:exp] = exp
    JWT.encode(payload, SECRET_KEY, ALGORITHM)
  end

  def self.decode(token)
    decoded = JWT.decode(token, SECRET_KEY, true, { algorithm: ALGORITHM })
    decoded.first
  rescue JWT::DecodeError, JWT::ExpiredSignature
    nil
  end
end
