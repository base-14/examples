module Api
  class CommentsController < BaseController
    skip_before_action :authenticate_user, only: [:index]
    before_action :set_article
    before_action :set_comment, only: [:destroy]
    before_action :authorize_comment, only: [:destroy]

    # GET /api/articles/:article_id/comments
    def index
      tracer.in_span('list_comments') do |span|
        span.set_attribute('article.id', @article.id)
        span.set_attribute('article.slug', @article.slug)

        comments = @article.comments.includes(:author).order(created_at: :desc)

        span.set_attribute('comments.count', comments.count)

        render_success({ comments: comments.map { |c| comment_response(c) } })
      end
    end

    # POST /api/articles/:article_id/comments
    def create
      tracer.in_span('create_comment') do |span|
        span.set_attribute('article.id', @article.id)
        span.set_attribute('article.slug', @article.slug)
        span.set_attribute('user.id', current_user.id)

        comment = @article.comments.build(comment_params.merge(author: current_user))

        if comment.save
          span.set_attribute('comment.id', comment.id)
          span.add_event('comment_created')

          render_success(comment_response(comment), {}, :created)
        else
          span.add_event('comment_creation_failed')
          render_validation_errors(comment)
        end
      end
    end

    # DELETE /api/articles/:article_id/comments/:id
    def destroy
      tracer.in_span('delete_comment') do |span|
        span.set_attribute('comment.id', @comment.id)
        span.set_attribute('article.id', @article.id)
        span.set_attribute('user.id', current_user.id)

        @comment.destroy!
        span.add_event('comment_deleted')

        render_success({ message: 'Comment deleted successfully' })
      end
    end

    private

    def set_article
      @article = Article.find_by!(slug: params[:article_id] || params[:article_slug])
    end

    def set_comment
      @comment = @article.comments.find(params[:id])
    end

    def authorize_comment
      unless @comment.author_id == current_user.id
        render_error('forbidden', 'You are not authorized to delete this comment', :forbidden)
      end
    end

    def comment_params
      params.require(:comment).permit(:body)
    end

    def comment_response(comment)
      {
        id: comment.id,
        body: comment.body,
        created_at: comment.created_at.iso8601,
        author: {
          id: comment.author.id,
          username: comment.author.username,
          image_url: comment.author.image_url
        }
      }
    end
  end
end
