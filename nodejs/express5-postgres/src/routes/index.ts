import { Router } from 'express';
import { healthRouter } from './health.js';
import { authRouter } from './auth.js';
import { articlesRouter } from './articles.js';

const router = Router();

router.use('/api', healthRouter);
router.use('/api', authRouter);
router.use('/api/articles', articlesRouter);

export { router };
