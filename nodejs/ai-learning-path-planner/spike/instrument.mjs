import { register } from 'node:module';
register('@opentelemetry/instrumentation/hook.mjs', import.meta.url);
await import('./telemetry.js');
