import './telemetry.js';

import { serve } from '@hono/node-server';
import { app } from './app.js';
import { config } from './config/index.js';

const start = async () => {
  try {
    serve({
      fetch: app.fetch,
      port: config.port,
      hostname: config.host,
    });

    console.log(`Server running at http://${config.host}:${config.port}`);
    console.log(`Environment: ${config.environment}`);
  } catch (err) {
    console.error('Failed to start server:', err);
    process.exit(1);
  }
};

start();
