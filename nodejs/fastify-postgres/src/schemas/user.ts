export const userResponseSchema = {
  type: 'object',
  properties: {
    id: { type: 'integer' },
    email: { type: 'string', format: 'email' },
    name: { type: 'string' },
    bio: { type: ['string', 'null'] },
    image: { type: ['string', 'null'] },
    createdAt: { type: 'string', format: 'date-time' },
  },
  required: ['id', 'email', 'name'],
} as const;

export const registerSchema = {
  body: {
    type: 'object',
    required: ['email', 'password', 'name'],
    properties: {
      email: { type: 'string', format: 'email' },
      password: {
        type: 'string',
        minLength: 8,
        maxLength: 128,
        pattern: '^(?=.*[a-z])(?=.*[A-Z])(?=.*\\d)(?=.*[^a-zA-Z\\d]).{8,}$',
        description: 'Must contain uppercase, lowercase, number, and special character',
      },
      name: { type: 'string', minLength: 1, maxLength: 255 },
    },
    additionalProperties: false,
  },
  response: {
    201: {
      type: 'object',
      properties: {
        user: userResponseSchema,
        token: { type: 'string' },
      },
      required: ['user', 'token'],
    },
    400: {
      type: 'object',
      properties: {
        error: { type: 'string' },
        message: { type: 'string' },
      },
    },
    409: {
      type: 'object',
      properties: {
        error: { type: 'string' },
        message: { type: 'string' },
      },
    },
  },
} as const;

export const loginSchema = {
  body: {
    type: 'object',
    required: ['email', 'password'],
    properties: {
      email: { type: 'string', format: 'email' },
      password: { type: 'string', minLength: 1 },
    },
    additionalProperties: false,
  },
  response: {
    200: {
      type: 'object',
      properties: {
        user: userResponseSchema,
        token: { type: 'string' },
      },
      required: ['user', 'token'],
    },
    401: {
      type: 'object',
      properties: {
        error: { type: 'string' },
        message: { type: 'string' },
      },
    },
  },
} as const;

export const getUserSchema = {
  response: {
    200: {
      type: 'object',
      properties: {
        user: userResponseSchema,
      },
      required: ['user'],
    },
    401: {
      type: 'object',
      properties: {
        error: { type: 'string' },
        message: { type: 'string' },
      },
    },
    404: {
      type: 'object',
      properties: {
        error: { type: 'string' },
        message: { type: 'string' },
      },
    },
  },
} as const;

export const updateUserSchema = {
  body: {
    type: 'object',
    properties: {
      name: { type: 'string', minLength: 1, maxLength: 255 },
      bio: { type: 'string', maxLength: 1000 },
      image: { type: 'string', format: 'uri', maxLength: 500 },
    },
    additionalProperties: false,
  },
  response: {
    200: {
      type: 'object',
      properties: {
        user: userResponseSchema,
      },
      required: ['user'],
    },
    401: {
      type: 'object',
      properties: {
        error: { type: 'string' },
        message: { type: 'string' },
      },
    },
  },
} as const;
