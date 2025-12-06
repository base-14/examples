import type { Request, Response, NextFunction } from 'express';
import { z, type ZodSchema } from 'zod';
import { ValidationError } from '../utils/errors.js';

export function validateBody<T extends ZodSchema>(schema: T) {
  return (req: Request, _res: Response, next: NextFunction): void => {
    try {
      const validated = schema.parse(req.body);
      req.body = validated;
      next();
    } catch (error) {
      if (error instanceof z.ZodError) {
        const errors = error.issues.map((err: z.ZodIssue) => `${err.path.join('.')}: ${err.message}`);
        next(new ValidationError(errors.join(', ')));
      } else {
        next(error);
      }
    }
  };
}

export function validateQuery<T extends ZodSchema>(schema: T) {
  return (req: Request, _res: Response, next: NextFunction): void => {
    try {
      const validated = schema.parse(req.query);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      req.query = validated as any;
      next();
    } catch (error) {
      if (error instanceof z.ZodError) {
        const errors = error.issues.map((err: z.ZodIssue) => `${err.path.join('.')}: ${err.message}`);
        next(new ValidationError(errors.join(', ')));
      } else {
        next(error);
      }
    }
  };
}
