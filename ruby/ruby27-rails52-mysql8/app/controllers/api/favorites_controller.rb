module Api
  class FavoritesController < BaseController
    before_action :set_article

    # POST /api/articles/:article_id/favorite
    def create
      tracer.in_span('favorite_article') do |span|
        span.set_attribute('article.id', @article.id)
        span.set_attribute('article.slug', @article.slug)
        span.set_attribute('user.id', current_user.id)

        @article.favorite_by(current_user)

        render_success(
          article_response(@article),
          { message: 'Article favorited successfully' }
        )
      end
    end

    # DELETE /api/articles/:article_id/favorite
    def destroy
      tracer.in_span('unfavorite_article') do |span|
        span.set_attribute('article.id', @article.id)
        span.set_attribute('article.slug', @article.slug)
        span.set_attribute('user.id', current_user.id)

        @article.unfavorite_by(current_user)

        render_success(
          article_response(@article),
          { message: 'Article unfavorited successfully' }
        )
      end
    end

    private

    def set_article
      @article = Article.find_by!(slug: params[:article_id] || params[:slug])
    end

    def article_response(article)
      {
        id: article.id,
        slug: article.slug,
        title: article.title,
        favorited: article.favorited_by?(current_user),
        favorites_count: article.favorites_count
      }
    end
  end
end
