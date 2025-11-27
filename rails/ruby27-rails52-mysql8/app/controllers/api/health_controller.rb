module Api
  class HealthController < BaseController
    def show
      health_status = build_health_status
      check_database_connection(health_status)
      check_redis_connection(health_status)

      render json: health_status
    end

    private

    def build_health_status
      {
        status: 'healthy',
        timestamp: Time.current.iso8601,
        version: ENV.fetch('OTEL_SERVICE_VERSION', '1.0.0'),
        service: ENV.fetch('OTEL_SERVICE_NAME', 'rails5-app')
      }
    end

    def check_database_connection(health_status)
      ActiveRecord::Base.connection.execute("SELECT 1 as health_check")
      health_status[:database] = 'connected'
    rescue => e
      health_status[:database] = 'disconnected'
      health_status[:status] = 'unhealthy'
    end

    def check_redis_connection(health_status)
      redis = Redis.new(url: ENV.fetch('REDIS_URL', 'redis://localhost:6379/0'))
      redis.set('health_check', Time.current.to_i, ex: 60)
      redis.get('health_check')
      redis.incr('health_check_count')
      health_status[:redis] = 'connected'
    rescue => e
      health_status[:redis] = 'disconnected'
      health_status[:status] = 'unhealthy'
    end
  end
end
