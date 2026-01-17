db = db.getSiblingDB('nextjs-api');

db.createCollection('users');
db.createCollection('articles');
db.createCollection('favorites');

db.users.createIndex({ email: 1 }, { unique: true });
db.users.createIndex({ username: 1 }, { unique: true });

db.articles.createIndex({ slug: 1 }, { unique: true });
db.articles.createIndex({ authorId: 1 });
db.articles.createIndex({ tags: 1 });
db.articles.createIndex({ createdAt: -1 });

db.favorites.createIndex({ userId: 1, articleId: 1 }, { unique: true });
db.favorites.createIndex({ articleId: 1 });

print('MongoDB initialized with collections and indexes');
