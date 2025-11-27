module Api
  class TagsController < BaseController
    skip_before_action :authenticate_user

    # GET /api/tags
    def index
      tracer.in_span('list_tags') do |span|
        tags = Tag.popular.limit(50)

        span.set_attribute('tags.count', tags.count)

        render_success({
          tags: tags.map { |t| { name: t.name, articles_count: t.articles.count } }
        })
      end
    end
  end
end
