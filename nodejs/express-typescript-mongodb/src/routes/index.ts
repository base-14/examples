import { Router } from 'express';
import healthRoutes from './health.routes.js';
import metricsRoutes from './metrics.routes.js';
import articleRoutes from './article.routes.js';
import authRoutes from './auth.routes.js';

const router = Router();

router.use('/api', healthRoutes);
router.use('/api', metricsRoutes);

const v1Router = Router();
v1Router.use('/auth', authRoutes);
v1Router.use('/articles', articleRoutes);
router.use('/api/v1', v1Router);

export default router;
