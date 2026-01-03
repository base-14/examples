module Api
  class ArticlesController < BaseController
    skip_before_action :authenticate_user, only: [:index, :show]
    before_action :optional_authentication, only: [:index, :show]
    before_action :set_article, only: [:show, :update, :destroy]
    before_action :authorize_article, only: [:update, :destroy]

    # GET /api/articles
    def index
      tracer.in_span('list_articles') do |span|
        articles = Article.includes(:author, :tags).recent

        # Apply filters
        articles = articles.by_author(params[:author_id]) if params[:author_id]
        articles = articles.tagged_with(params[:tag]) if params[:tag]
        articles = articles.favorited_by(params[:favorited_by]) if params[:favorited_by]

        # Paginate
        page = params[:page] || 1
        per_page = [params[:per_page].to_i, 100].min
        per_page = 20 if per_page <= 0

        articles = articles.page(page).per(per_page)

        span.set_attribute('articles.count', articles.count)
        span.set_attribute('articles.page', page)
        span.set_attribute('articles.per_page', per_page)
        span.set_attribute('articles.total_pages', articles.total_pages)

        render_success(
          { articles: articles.map { |a| article_response(a) } },
          pagination_meta(articles)
        )
      end
    end

    # GET /api/articles/:slug
    def show
      tracer.in_span('get_article') do |span|
        span.set_attribute('article.id', @article.id)
        span.set_attribute('article.slug', @article.slug)

        render_success(article_response(@article))
      end
    end

    # POST /api/articles
    def create
      tracer.in_span('create_article') do |span|
        article = current_user.articles.build(article_params)

        # Handle tags
        if params[:article][:tag_list].present?
          tag_names = params[:article][:tag_list].split(',').map(&:strip)
          article.tags = tag_names.map { |name| Tag.find_or_create_by(name: name.downcase) }
        end

        if article.save
          span.set_attribute('article.id', article.id)
          span.set_attribute('article.slug', article.slug)
          span.set_attribute('article.tags_count', article.tags.count)
          span.add_event('article_created')

          render_success(article_response(article), {}, :created)
        else
          span.add_event('article_creation_failed')
          render_validation_errors(article)
        end
      end
    end

    # PUT /api/articles/:slug
    def update
      tracer.in_span('update_article') do |span|
        span.set_attribute('article.id', @article.id)
        span.set_attribute('article.slug', @article.slug)

        # Handle tags if provided
        if params[:article][:tag_list].present?
          tag_names = params[:article][:tag_list].split(',').map(&:strip)
          @article.tags = tag_names.map { |name| Tag.find_or_create_by(name: name.downcase) }
        end

        if @article.update(article_params)
          span.add_event('article_updated')
          render_success(article_response(@article))
        else
          span.add_event('article_update_failed')
          render_validation_errors(@article)
        end
      end
    end

    # DELETE /api/articles/:slug
    def destroy
      tracer.in_span('delete_article') do |span|
        span.set_attribute('article.id', @article.id)
        span.set_attribute('article.slug', @article.slug)

        @article.destroy!
        span.add_event('article_deleted')

        render_success({ message: 'Article deleted successfully' })
      end
    end

    private

    def set_article
      @article = Article.includes(:author, :tags).find_by!(slug: params[:slug] || params[:id])
    end

    def authorize_article
      unless @article.author_id == current_user.id
        render_error('forbidden', 'You are not authorized to perform this action', :forbidden)
      end
    end

    def article_params
      params.require(:article).permit(:title, :description, :body)
    end

    def article_response(article)
      {
        id: article.id,
        slug: article.slug,
        title: article.title,
        description: article.description,
        body: article.body,
        tags: article.tags.pluck(:name),
        created_at: article.created_at.iso8601,
        updated_at: article.updated_at.iso8601,
        favorited: current_user ? article.favorited_by?(current_user) : false,
        favorites_count: article.favorites_count,
        author: {
          id: article.author.id,
          username: article.author.username,
          bio: article.author.bio,
          image_url: article.author.image_url
        }
      }
    end

    def pagination_meta(collection)
      {
        page: collection.current_page,
        per_page: collection.limit_value,
        total_pages: collection.total_pages,
        total_count: collection.total_count
      }
    end
  end
end
