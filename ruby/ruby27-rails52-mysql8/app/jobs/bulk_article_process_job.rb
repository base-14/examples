class BulkArticleProcessJob < ApplicationJob
  queue_as :default

  MAX_THREADS = 5

  def perform(article_ids, operation = 'analyze')
    Article

    results = []
    errors = []

    parent_context = OpenTelemetry::Context.current

    article_ids.each_slice(MAX_THREADS) do |batch|
      # Note: Ruby 2.7 + SimpleSpanProcessor doesn't support proper context propagation to threads.
      # Each thread creates a separate trace. Thread spans include parent.trace_id attribute to
      # correlate with the parent Sidekiq job. Use Ruby 3.0+ with BatchSpanProcessor for full trace hierarchy.
      threads = batch.map do |article_id|
        Thread.new(parent_context) do |ctx|
          OpenTelemetry::Context.with_current(ctx) do
            begin
              process_article_in_thread(article_id, operation)
            rescue => e
              { article_id: article_id, error: e.message }
            end
          end
        end
      end

      batch_results = threads.map(&:value)
      batch_results.each do |result|
        if result.is_a?(Hash) && result[:error]
          errors << result
        else
          results << result
        end
      end
    end

    Rails.logger.info "BulkArticleProcessJob completed: #{results.size} successful, #{errors.size} errors"

    { success: results, errors: errors }
  end

  private

  def process_article_in_thread(article_id, operation)
    tracer.in_span("process_article_#{operation}", attributes: {
      'article.id' => article_id,
      'article.operation' => operation,
      'thread.id' => Thread.current.object_id
    }) do |span|

      article = Article.find_by(id: article_id)

      unless article
        span.set_attribute('article.found', false)
        return nil
      end

      span.set_attribute('article.found', true)
      span.set_attribute('article.title', article.title)

      case operation
      when 'analyze'
        call_sentiment_analysis_api(article)
      when 'translate'
        call_translation_api(article)
      when 'moderate'
        call_moderation_api(article)
      else
        span.add_event('unknown_operation')
      end

      span.add_event('article_processed')
      { article_id: article_id, title: article.title, status: 'processed' }
    end
  end

  def call_sentiment_analysis_api(article)
    tracer.in_span('external_api.sentiment_analysis', kind: :client, attributes: {
      'http.url' => 'https://api.example.com/sentiment',
      'http.method' => 'POST',
      'article.id' => article.id,
      'thread.id' => Thread.current.object_id
    }) do |span|
      sleep(rand(0.1..0.3))

      sentiment = ['positive', 'negative', 'neutral'].sample
      span.set_attribute('http.status_code', 200)
      span.set_attribute('analysis.sentiment', sentiment)
      span.add_event('sentiment_analyzed', attributes: { 'sentiment' => sentiment })
    end
  end

  def call_translation_api(article)
    tracer.in_span('external_api.translation', kind: :client, attributes: {
      'http.url' => 'https://api.example.com/translate',
      'http.method' => 'POST',
      'article.id' => article.id,
      'translation.target_language' => 'es',
      'thread.id' => Thread.current.object_id
    }) do |span|
      sleep(rand(0.2..0.4))

      span.set_attribute('http.status_code', 200)
      span.set_attribute('translation.word_count', article.body.split.size)
      span.add_event('article_translated')
    end
  end

  def call_moderation_api(article)
    tracer.in_span('external_api.moderation', kind: :client, attributes: {
      'http.url' => 'https://api.example.com/moderate',
      'http.method' => 'POST',
      'article.id' => article.id,
      'thread.id' => Thread.current.object_id
    }) do |span|
      sleep(rand(0.1..0.2))

      is_safe = [true, true, true, false].sample
      span.set_attribute('http.status_code', 200)
      span.set_attribute('moderation.is_safe', is_safe)
      span.add_event('content_moderated', attributes: { 'is_safe' => is_safe })
    end
  end
end
