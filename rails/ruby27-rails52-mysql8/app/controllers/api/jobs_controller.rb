module Api
  class JobsController < BaseController
    def create
      user_id = params[:user_id] || rand(1..1000)
      action = params[:action_name] || 'process_data'

      # Enqueue job with tracing context
      job_id = ExampleJob.perform_async(user_id, action)

      add_trace_attributes(
        'job.id' => job_id,
        'job.user_id' => user_id,
        'job.action' => action,
        'job.queue' => 'default'
      )

      record_trace_event('job_enqueued', {
        'job.id' => job_id,
        'job.class' => 'ExampleJob'
      })

      render json: {
        status: 'enqueued',
        job_id: job_id,
        user_id: user_id,
        action: action
      }
    end
  end
end
