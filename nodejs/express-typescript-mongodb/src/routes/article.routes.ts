import { Router } from 'express';
import {
  createArticle,
  listArticles,
  getArticle,
  updateArticle,
  deleteArticle,
  publishArticle,
  favoriteArticle,
  unfavoriteArticle,
} from '../controllers/article.controller.js';
import { authenticate } from '../middleware/auth.middleware.js';
import { validateBody } from '../middleware/validation.middleware.js';
import { articleInputSchema, articleUpdateSchema } from '../validation/zod-schemas.js';

const router = Router();

router.get('/', listArticles);
router.post('/', authenticate, validateBody(articleInputSchema), createArticle);
router.get('/:id', getArticle);
router.put('/:id', authenticate, validateBody(articleUpdateSchema), updateArticle);
router.delete('/:id', authenticate, deleteArticle);
router.post('/:id/publish', authenticate, publishArticle);
router.post('/:id/favorite', authenticate, favoriteArticle);
router.delete('/:id/favorite', authenticate, unfavoriteArticle);

export default router;
