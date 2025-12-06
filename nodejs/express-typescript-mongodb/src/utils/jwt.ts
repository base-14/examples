import jwt from 'jsonwebtoken';
import { z } from 'zod';
import { config } from '../config.js';
import { AuthenticationError } from './errors.js';

const { JsonWebTokenError, TokenExpiredError } = jwt;

const jwtPayloadSchema = z.object({
  userId: z.string(),
  email: z.string().email(),
  role: z.string(),
  iat: z.number().optional(),
  exp: z.number().optional(),
});

export type JWTPayload = z.infer<typeof jwtPayloadSchema>;

/** Generates signed JWT token from user payload (userId, email, role) */
export function generateToken(payload: Omit<JWTPayload, 'iat' | 'exp'>): string {
  const options: jwt.SignOptions = {
    algorithm: 'HS256',
    expiresIn: config.jwt.expiresIn as jwt.SignOptions['expiresIn'],
  };
  return jwt.sign(payload, config.jwt.secret, options);
}

/** Verifies JWT token and validates payload structure with Zod */
export function verifyToken(token: string): JWTPayload {
  try {
    const decoded = jwt.verify(token, config.jwt.secret);

    // Runtime validation of payload structure
    const parseResult = jwtPayloadSchema.safeParse(decoded);

    if (!parseResult.success) {
      throw new AuthenticationError('Invalid token payload structure');
    }

    return parseResult.data;
  } catch (error) {
    if (error instanceof JsonWebTokenError) {
      throw new AuthenticationError('Invalid token');
    }
    if (error instanceof TokenExpiredError) {
      throw new AuthenticationError('Token expired');
    }
    throw error;
  }
}
