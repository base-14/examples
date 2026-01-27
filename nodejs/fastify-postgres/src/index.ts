import './telemetry.js';

import { createApp } from './app.js';
import { config } from './config/index.js';

const start = async () => {
  try {
    const app = await createApp();

    await app.listen({ port: config.port, host: config.host });

    app.log.info(`Server running at http://${config.host}:${config.port}`);
    app.log.info(`Environment: ${config.environment}`);
  } catch (err) {
    console.error('Failed to start server:', err);
    process.exit(1);
  }
};

start();
