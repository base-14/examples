import express from 'express';
import cors from 'cors';
import pino from 'pino';
import { pool } from './db';

const app = express();

// Auto-bridged + trace-correlated by instrumentation-pino (via the -r preload).
const log = pino();

// allowedHeaders must include traceparent/tracestate so the browser fetch can
// propagate trace context and stay in one trace with the server span.
app.use(
  cors({
    origin: ['http://localhost:4200', 'http://localhost:8080'],
    allowedHeaders: ['Content-Type', 'traceparent', 'tracestate'],
  }),
);

app.get('/api/items', async (_req, res) => {
  const { rows } = await pool.query('SELECT id, name, price FROM items ORDER BY id');
  log.info({ count: rows.length }, 'served items');
  res.json(rows);
});

app.get('/healthz', (_req, res) => {
  res.json({ ok: true });
});

const port = Number(process.env.PORT || 3000);
app.listen(port, () => log.info(`angular-items-api listening on :${port}`));
