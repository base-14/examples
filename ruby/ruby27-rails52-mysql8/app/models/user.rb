class User < ApplicationRecord
  has_secure_password

  # Associations
  has_many :articles, foreign_key: :author_id, dependent: :destroy
  has_many :comments, foreign_key: :author_id, dependent: :destroy
  has_many :favorites, dependent: :destroy
  has_many :favorited_articles, through: :favorites, source: :article

  has_many :follower_relationships, class_name: 'Follow', foreign_key: :followee_id, dependent: :destroy
  has_many :followers, through: :follower_relationships, source: :follower

  has_many :followee_relationships, class_name: 'Follow', foreign_key: :follower_id, dependent: :destroy
  has_many :following, through: :followee_relationships, source: :followee

  # Validations
  validates :email, presence: true, uniqueness: { case_sensitive: false },
            format: { with: URI::MailTo::EMAIL_REGEXP }
  validates :username, presence: true, uniqueness: { case_sensitive: false },
            length: { minimum: 3, maximum: 50 },
            format: { with: /\A[a-zA-Z0-9_-]+\z/, message: 'only allows letters, numbers, underscores, and hyphens' }
  validates :password, length: { minimum: 8 }, if: -> { new_record? || !password.nil? }
  validates :bio, length: { maximum: 500 }, allow_blank: true

  # Callbacks
  before_save :downcase_email

  # Instance methods
  def generate_jwt
    tracer.in_span('user.generate_jwt', attributes: { 'user.id' => id }) do |span|
      token = JwtConfig.encode({ user_id: id, email: email })
      span.set_attribute('jwt.generated', true)
      token
    end
  end

  def following?(other_user)
    following.include?(other_user)
  end

  def follow(other_user)
    tracer.in_span('user.follow', attributes: {
      'user.id' => id,
      'target_user.id' => other_user.id
    }) do
      following << other_user unless following?(other_user)
    end
  end

  def unfollow(other_user)
    tracer.in_span('user.unfollow', attributes: {
      'user.id' => id,
      'target_user.id' => other_user.id
    }) do
      following.delete(other_user)
    end
  end

  def favorited?(article)
    favorited_articles.include?(article)
  end

  private

  def downcase_email
    self.email = email.downcase
  end

  def tracer
    @tracer ||= OpenTelemetryHelper.tracer
  end
end
