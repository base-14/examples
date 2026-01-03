class Article < ApplicationRecord
  belongs_to :author, class_name: 'User'
  has_many :comments, dependent: :destroy
  has_many :article_tags, dependent: :destroy
  has_many :tags, through: :article_tags
  has_many :favorites, dependent: :destroy
  has_many :favorited_by, through: :favorites, source: :user

  # Validations
  validates :title, presence: true, length: { maximum: 200 }
  validates :description, presence: true, length: { maximum: 1000 }
  validates :body, presence: true
  validates :slug, presence: true, uniqueness: true

  # Callbacks
  before_validation :generate_slug, on: :create
  after_create :record_creation_event

  # Scopes
  scope :recent, -> { order(created_at: :desc) }
  scope :by_author, ->(author_id) { where(author_id: author_id) }
  scope :favorited_by, ->(user_id) { joins(:favorites).where(favorites: { user_id: user_id }) }
  scope :tagged_with, ->(tag_name) { joins(:tags).where(tags: { name: tag_name }) }

  # Instance methods
  def favorited_by?(user)
    return false unless user
    favorited_by.include?(user)
  end

  def favorite_by(user)
    tracer.in_span('article.favorite', attributes: {
      'article.id' => id,
      'article.slug' => slug,
      'user.id' => user.id
    }) do |span|
      return if favorited_by?(user)

      favorites.create!(user: user)
      increment!(:favorites_count)

      span.set_attribute('article.favorites_count', favorites_count)
      span.add_event('article_favorited')
    end
  end

  def unfavorite_by(user)
    tracer.in_span('article.unfavorite', attributes: {
      'article.id' => id,
      'article.slug' => slug,
      'user.id' => user.id
    }) do |span|
      favorite = favorites.find_by(user: user)
      return unless favorite

      favorite.destroy!
      decrement!(:favorites_count)

      span.set_attribute('article.favorites_count', favorites_count)
      span.add_event('article_unfavorited')
    end
  end

  private

  def generate_slug
    return if slug.present?

    base_slug = title.parameterize
    slug_candidate = base_slug
    counter = 1

    while Article.exists?(slug: slug_candidate)
      slug_candidate = "#{base_slug}-#{counter}"
      counter += 1
    end

    self.slug = slug_candidate
  end

  def record_creation_event
    tracer.in_span('article.created', attributes: {
      'article.id' => id,
      'article.slug' => slug,
      'article.author_id' => author_id,
      'article.tags_count' => tags.count
    }) do |span|
      span.add_event('new_article_published')
    end
  end

  def tracer
    @tracer ||= OpenTelemetryHelper.tracer
  end
end
