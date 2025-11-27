class ExampleJob < ApplicationJob
  queue_as :default

  def perform(user_id, action)
    tracer.in_span('example_job.processing', attributes: {
      'job.user_id' => user_id,
      'job.action' => action
    }) do |span|
      # Simulate some work
      sleep_duration = rand(0.1..0.5)
      span.set_attribute('job.sleep_duration', sleep_duration)
      sleep(sleep_duration)

      # Simulate database work (will be auto-instrumented)
      tracer.in_span('fetch_user_data') do
        ActiveRecord::Base.connection.execute("SELECT 1")
      end

      # Simulate external API call
      tracer.in_span('call_external_api', kind: :client, attributes: {
        'http.url' => 'https://api.example.com/users',
        'http.method' => 'GET'
      }) do |api_span|
        sleep(0.1)
        api_span.set_attribute('http.status_code', 200)
      end

      span.add_event('job_completed', attributes: { 'result' => 'success' })
    end
  end
end
