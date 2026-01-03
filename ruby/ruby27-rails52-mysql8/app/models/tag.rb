class Tag < ApplicationRecord
  has_many :article_tags, dependent: :destroy
  has_many :articles, through: :article_tags

  validates :name, presence: true, uniqueness: { case_sensitive: false },
            length: { maximum: 50 },
            format: { with: /\A[a-z0-9-]+\z/, message: 'only allows lowercase letters, numbers, and hyphens' }

  before_validation :downcase_name

  scope :popular, -> {
    joins(:article_tags)
      .group('tags.id')
      .order('COUNT(article_tags.id) DESC')
  }

  private

  def downcase_name
    self.name = name.downcase if name
  end
end
