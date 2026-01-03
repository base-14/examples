class Comment < ApplicationRecord
  belongs_to :article
  belongs_to :author, class_name: 'User'

  validates :body, presence: true, length: { maximum: 2000 }

  after_create :record_comment_event

  private

  def record_comment_event
    tracer = OpenTelemetryHelper.tracer
    tracer.in_span('comment.created', attributes: {
      'comment.id' => id,
      'article.id' => article_id,
      'article.slug' => article.slug,
      'author.id' => author_id
    }) do |span|
      span.add_event('article_commented')
    end
  end
end
