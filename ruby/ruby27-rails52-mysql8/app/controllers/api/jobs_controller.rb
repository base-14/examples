module Api
  class JobsController < BaseController
    skip_before_action :authenticate_user, only: [:create, :bulk_process]

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

    def bulk_process
      count = params[:count]&.to_i || 10
      operation = params[:operation] || 'analyze'

      article_ids = Article.order('RAND()').limit(count).pluck(:id)

      if article_ids.empty?
        return render json: {
          error: 'No articles found in database'
        }, status: :not_found
      end

      job_id = BulkArticleProcessJob.perform_async(article_ids, operation)

      add_trace_attributes(
        'job.id' => job_id,
        'job.article_count' => article_ids.size,
        'job.operation' => operation,
        'job.queue' => 'default'
      )

      record_trace_event('bulk_job_enqueued', {
        'job.id' => job_id,
        'job.class' => 'BulkArticleProcessJob',
        'job.article_ids' => article_ids
      })

      render json: {
        status: 'enqueued',
        job_id: job_id,
        article_count: article_ids.size,
        article_ids: article_ids,
        operation: operation,
        message: "Processing #{article_ids.size} articles with operation '#{operation}' using concurrent threads"
      }
    end
  end
end
