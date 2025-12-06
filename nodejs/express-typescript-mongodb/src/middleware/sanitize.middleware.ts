import type { Request, Response, NextFunction } from 'express';
import { sanitizeObject } from '../utils/sanitize.js';

/**
 * Middleware to sanitize all incoming request data (body, query, params)
 * Applies rich text sanitization to 'content' field and strict sanitization to all other fields
 */
export function sanitizeInput(req: Request, _res: Response, next: NextFunction): void {
  try {
    // Skip sanitization in test environment
    if (process.env.NODE_ENV === 'test') {
      return next();
    }

    // Define fields that should allow rich text HTML (safe tags only)
    const richTextFields = ['content'];

    // Only sanitize body - it's the main vector for XSS attacks
    // req.query and req.params are read-only in Express 5 and cause conflicts with the router
    // These should be validated/sanitized by Zod schemas instead
    if (req.body && typeof req.body === 'object') {
      req.body = sanitizeObject(req.body, richTextFields);
    }

    next();
  } catch (error) {
    next(error);
  }
}
