# db/seeds.rb
# Comprehensive seed data for Rails 5.2 OpenTelemetry Example

require 'securerandom'

puts "🌱 Starting seed data generation..."

# Clear existing data
puts "Clearing existing data..."
[ArticleTag, Favorite, Follow, Comment, Article, Tag, User].each(&:delete_all)

# Create Tags
puts "Creating tags..."
tags = [
  'ruby', 'rails', 'javascript', 'python', 'golang', 'nodejs',
  'docker', 'kubernetes', 'aws', 'microservices', 'api', 'testing',
  'devops', 'cicd', 'monitoring', 'observability', 'opentelemetry',
  'databases', 'mysql', 'postgresql', 'redis', 'performance'
].map { |name| Tag.create!(name: name) }

puts "✅ Created #{tags.count} tags"

# Create Users
puts "Creating users..."
users = []

# Create admin user
admin = User.create!(
  email: 'admin@example.com',
  username: 'admin',
  password: 'password123',
  bio: 'Platform administrator and OpenTelemetry enthusiast',
  image_url: 'https://api.dicebear.com/7.x/avataaars/svg?seed=admin'
)
users << admin

# Create regular users
user_data = [
  { email: 'alice@example.com', username: 'alice', bio: 'Full-stack developer passionate about Ruby and Rails' },
  { email: 'bob@example.com', username: 'bob', bio: 'Backend engineer specializing in distributed systems' },
  { email: 'carol@example.com', username: 'carol', bio: 'DevOps engineer focused on observability and monitoring' },
  { email: 'dave@example.com', username: 'dave', bio: 'Frontend developer exploring modern JavaScript frameworks' },
  { email: 'eve@example.com', username: 'eve', bio: 'Site reliability engineer with a focus on automation' },
  { email: 'frank@example.com', username: 'frank', bio: 'Database administrator optimizing query performance' },
  { email: 'grace@example.com', username: 'grace', bio: 'Security engineer implementing best practices' },
  { email: 'henry@example.com', username: 'henry', bio: 'Cloud architect designing scalable solutions' },
  { email: 'iris@example.com', username: 'iris', bio: 'Tech writer documenting complex systems' },
  { email: 'jack@example.com', username: 'jack', bio: 'QA engineer ensuring quality through testing' }
]

user_data.each do |data|
  users << User.create!(
    email: data[:email],
    username: data[:username],
    password: 'password123',
    bio: data[:bio],
    image_url: "https://api.dicebear.com/7.x/avataaars/svg?seed=#{data[:username]}"
  )
end

puts "✅ Created #{users.count} users"

# Create follow relationships
puts "Creating follow relationships..."
follow_count = 0
users.each do |follower|
  # Each user follows 2-5 random other users
  users.sample(rand(2..5)).each do |followee|
    next if follower == followee
    next if follower.following?(followee)

    follower.follow(followee)
    follow_count += 1
  end
end

puts "✅ Created #{follow_count} follow relationships"

# Create Articles
puts "Creating articles..."
articles = []

article_templates = [
  {
    title: "Getting Started with OpenTelemetry in Rails",
    description: "A comprehensive guide to instrumenting your Rails application with OpenTelemetry",
    body: "OpenTelemetry provides a unified approach to collecting traces, metrics, and logs from your applications. In this article, we'll explore how to integrate OpenTelemetry with Rails 5.2.\n\n## Installation\n\nFirst, add the necessary gems to your Gemfile...\n\n## Configuration\n\nCreate an initializer to configure OpenTelemetry...\n\n## Best Practices\n\nHere are some best practices for instrumenting your Rails application...",
    tags: ['opentelemetry', 'rails', 'observability', 'monitoring']
  },
  {
    title: "Building RESTful APIs with Rails",
    description: "Best practices for designing and implementing REST APIs in Rails",
    body: "REST APIs are the backbone of modern web applications. This guide covers authentication, versioning, error handling, and more.\n\n## API Design Principles\n\nFollow these principles when designing your API...\n\n## Authentication\n\nWe recommend using JWT tokens for stateless authentication...\n\n## Error Handling\n\nConsistent error responses improve developer experience...",
    tags: ['rails', 'api', 'rest']
  },
  {
    title: "MySQL 8 Performance Optimization",
    description: "Tips and tricks for optimizing MySQL 8 query performance",
    body: "MySQL 8 introduces many performance improvements. Learn how to leverage them for faster queries.\n\n## Indexing Strategies\n\nProper indexing is crucial for query performance...\n\n## Query Optimization\n\nUse EXPLAIN to understand query execution plans...\n\n## Configuration Tuning\n\nAdjust these parameters for better performance...",
    tags: ['mysql', 'databases', 'performance']
  },
  {
    title: "Docker Best Practices for Ruby Applications",
    description: "Optimizing Docker images and containers for Ruby on Rails",
    body: "Docker has become essential for modern application deployment. Learn how to optimize your Ruby containers.\n\n## Multi-stage Builds\n\nReduce image size with multi-stage builds...\n\n## Caching Strategies\n\nLeverage Docker's layer caching...\n\n## Security Considerations\n\nFollow these security best practices...",
    tags: ['docker', 'ruby', 'devops']
  },
  {
    title: "Implementing CI/CD for Rails Applications",
    description: "Setting up continuous integration and deployment pipelines",
    body: "Automated testing and deployment improve development velocity and code quality.\n\n## Pipeline Setup\n\nConfigure your CI/CD pipeline with these steps...\n\n## Testing Strategy\n\nEnsure comprehensive test coverage...\n\n## Deployment Automation\n\nAutomate deployments safely...",
    tags: ['cicd', 'rails', 'devops', 'testing']
  },
  {
    title: "Microservices Architecture with Rails",
    description: "Transitioning from monolith to microservices",
    body: "Microservices can improve scalability and maintainability when done right.\n\n## When to Use Microservices\n\nConsider these factors...\n\n## Service Communication\n\nChoose the right communication patterns...\n\n## Data Management\n\nHandle distributed data correctly...",
    tags: ['microservices', 'rails', 'architecture']
  }
]

# Create 3 articles per template with different authors
article_templates.each do |template|
  3.times do
    author = users.sample
    article = author.articles.create!(
      title: "#{template[:title]} #{['Part 1', 'Part 2', 'Advanced Guide'].sample}",
      description: template[:description],
      body: template[:body]
    )

    # Add tags
    template[:tags].each do |tag_name|
      tag = tags.find { |t| t.name == tag_name }
      article.tags << tag if tag
    end

    articles << article
  end
end

# Add some unique articles
unique_articles = [
  {
    author: admin,
    title: "Welcome to Our Tech Blog",
    description: "Introduction to our new technical blog focused on Rails and observability",
    body: "Welcome! We're excited to share our knowledge about Rails, OpenTelemetry, and modern development practices.",
    tags: ['rails', 'opentelemetry']
  },
  {
    author: users[1],
    title: "My Journey Learning Rails",
    description: "A beginner's perspective on learning Ruby on Rails in 2024",
    body: "I started learning Rails three months ago, and here's what I've discovered...",
    tags: ['rails', 'ruby']
  }
]

unique_articles.each do |data|
  article = data[:author].articles.create!(
    title: data[:title],
    description: data[:description],
    body: data[:body]
  )

  data[:tags].each do |tag_name|
    tag = tags.find { |t| t.name == tag_name }
    article.tags << tag if tag
  end

  articles << article
end

puts "✅ Created #{articles.count} articles"

# Create Comments
puts "Creating comments..."
comment_count = 0

comment_templates = [
  "Great article! This really helped me understand the concept.",
  "Thanks for sharing. I've been looking for information on this topic.",
  "Excellent explanation. Could you elaborate more on the performance implications?",
  "This is exactly what I needed for my current project.",
  "Well written! Looking forward to more articles like this.",
  "I tried implementing this and it worked perfectly.",
  "One suggestion: you might want to mention the potential pitfalls.",
  "This approach has worked well for us in production.",
  "Clear and concise. Thank you!",
  "Have you considered the security implications?",
  "I'd love to see a follow-up article on advanced techniques.",
  "This saved me hours of debugging. Much appreciated!",
  "Good overview, but I think you missed an important edge case.",
  "Bookmarking this for future reference.",
  "The code examples are very helpful."
]

articles.each do |article|
  # Each article gets 0-8 comments
  rand(0..8).times do
    commenter = users.sample
    next if commenter == article.author && rand > 0.3 # Authors rarely comment on their own articles

    article.comments.create!(
      author: commenter,
      body: comment_templates.sample
    )
    comment_count += 1
  end
end

puts "✅ Created #{comment_count} comments"

# Create Favorites
puts "Creating favorites..."
favorite_count = 0

articles.each do |article|
  # Each article gets favorited by 0-7 random users
  users.sample(rand(0..7)).each do |user|
    next if user == article.author # Authors don't favorite their own articles
    next if article.favorited_by?(user)

    article.favorite_by(user)
    favorite_count += 1
  end
end

puts "✅ Created #{favorite_count} favorites"

# Print summary
puts "\n" + "="*50
puts "🎉 Seed data generation complete!"
puts "="*50
puts "Users:       #{User.count}"
puts "Articles:    #{Article.count}"
puts "Comments:    #{Comment.count}"
puts "Tags:        #{Tag.count}"
puts "Favorites:   #{Favorite.count}"
puts "Follows:     #{Follow.count}"
puts "="*50
puts "\nSample credentials:"
puts "Email:    admin@example.com"
puts "Password: password123"
puts "\n(All users have the same password: password123)"
puts "="*50
