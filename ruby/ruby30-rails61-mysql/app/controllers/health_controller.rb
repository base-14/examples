class HealthController < ApplicationController
  def show
    render json: {
      status: "healthy",
      service: {
        name: ENV.fetch("OTEL_SERVICE_NAME", "ruby30-rails61-mysql-otel"),
        version: Rails.version
      }
    }
  end
end
