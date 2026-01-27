const authorSchema = {
  type: 'object',
  properties: {
    id: { type: 'integer' },
    name: { type: 'string' },
    bio: { type: ['string', 'null'] },
    image: { type: ['string', 'null'] },
  },
  required: ['id', 'name'],
} as const;

const articleResponseSchema = {
  type: 'object',
  properties: {
    id: { type: 'integer' },
    slug: { type: 'string' },
    title: { type: 'string' },
    description: { type: ['string', 'null'] },
    body: { type: 'string' },
    favoritesCount: { type: 'integer' },
    createdAt: { type: 'string', format: 'date-time' },
    updatedAt: { type: 'string', format: 'date-time' },
    author: authorSchema,
    favorited: { type: 'boolean' },
  },
  required: ['id', 'slug', 'title', 'body', 'favoritesCount', 'author', 'favorited'],
} as const;

const errorSchema = {
  type: 'object',
  properties: {
    error: { type: 'string' },
    message: { type: 'string' },
  },
} as const;

export const listArticlesSchema = {
  querystring: {
    type: 'object',
    properties: {
      limit: { type: 'integer', minimum: 1, maximum: 100, default: 20 },
      offset: { type: 'integer', minimum: 0, default: 0 },
      author: { type: 'string' },
      favorited: { type: 'string' },
    },
    additionalProperties: false,
  },
  response: {
    200: {
      type: 'object',
      properties: {
        articles: {
          type: 'array',
          items: articleResponseSchema,
        },
        articlesCount: { type: 'integer' },
      },
      required: ['articles', 'articlesCount'],
    },
  },
} as const;

export const getArticleSchema = {
  params: {
    type: 'object',
    required: ['slug'],
    properties: {
      slug: { type: 'string' },
    },
  },
  response: {
    200: {
      type: 'object',
      properties: {
        article: articleResponseSchema,
      },
      required: ['article'],
    },
    404: errorSchema,
  },
} as const;

export const createArticleSchema = {
  body: {
    type: 'object',
    required: ['title', 'body'],
    properties: {
      title: { type: 'string', minLength: 1, maxLength: 255 },
      description: { type: 'string', maxLength: 1000 },
      body: { type: 'string', minLength: 1 },
    },
    additionalProperties: false,
  },
  response: {
    201: {
      type: 'object',
      properties: {
        article: articleResponseSchema,
      },
      required: ['article'],
    },
    400: errorSchema,
    401: errorSchema,
  },
} as const;

export const updateArticleSchema = {
  params: {
    type: 'object',
    required: ['slug'],
    properties: {
      slug: { type: 'string' },
    },
  },
  body: {
    type: 'object',
    properties: {
      title: { type: 'string', minLength: 1, maxLength: 255 },
      description: { type: 'string', maxLength: 1000 },
      body: { type: 'string', minLength: 1 },
    },
    additionalProperties: false,
  },
  response: {
    200: {
      type: 'object',
      properties: {
        article: articleResponseSchema,
      },
      required: ['article'],
    },
    401: errorSchema,
    403: errorSchema,
    404: errorSchema,
  },
} as const;

export const deleteArticleSchema = {
  params: {
    type: 'object',
    required: ['slug'],
    properties: {
      slug: { type: 'string' },
    },
  },
  response: {
    204: {
      type: 'null',
    },
    401: errorSchema,
    403: errorSchema,
    404: errorSchema,
  },
} as const;

export const favoriteArticleSchema = {
  params: {
    type: 'object',
    required: ['slug'],
    properties: {
      slug: { type: 'string' },
    },
  },
  response: {
    200: {
      type: 'object',
      properties: {
        article: articleResponseSchema,
      },
      required: ['article'],
    },
    401: errorSchema,
    404: errorSchema,
  },
} as const;
