import { z } from 'zod';
import { config } from '../config.js';

export const articleInputSchema = z.object({
  title: z.string().trim().min(1, 'Title is required').max(200, 'Title must be at most 200 characters'),
  content: z.string().trim().min(1, 'Content is required').max(50000, 'Content must be at most 50000 characters'),
  tags: z.array(z.string()).optional().default([]),
});

export const registerInputSchema = z.object({
  email: z.string().email('Invalid email format').toLowerCase().trim(),
  password: z.string().min(config.auth.minPasswordLength, `Password must be at least ${config.auth.minPasswordLength} characters`),
  name: z.string().trim().min(1, 'Name is required'),
});

export const loginInputSchema = z.object({
  email: z.string().email('Invalid email format').toLowerCase().trim(),
  password: z.string().min(1, 'Password is required'),
});

export const articleUpdateSchema = z.object({
  title: z.string().trim().min(1, 'Title is required').max(200, 'Title must be at most 200 characters').optional(),
  content: z.string().trim().min(1, 'Content is required').max(50000, 'Content must be at most 50000 characters').optional(),
  tags: z.array(z.string()).optional(),
}).refine((data) => data.title || data.content || data.tags, {
  message: 'At least one field must be provided for update',
});

export const paginationSchema = z.object({
  page: z.coerce.number().int().min(1).optional().default(1),
  limit: z.coerce.number().int().min(1).max(config.pagination.maxLimit).optional().default(config.pagination.defaultLimit),
});

export type ArticleInput = z.infer<typeof articleInputSchema>;
export type RegisterInput = z.infer<typeof registerInputSchema>;
export type LoginInput = z.infer<typeof loginInputSchema>;
export type ArticleUpdateInput = z.infer<typeof articleUpdateSchema>;
export type PaginationInput = z.infer<typeof paginationSchema>;
