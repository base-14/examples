// Production build config (used by `ng build`). The browser runs on the host in
// every mode of this example, so the collector/API are reached via localhost.
// The whole local stack runs as a single `development` environment (matching the
// backend DEPLOY_ENV and the collector's SCOUT_ENVIRONMENT default) so one trace
// carries one environment. For a real deployment, set this to `production` and
// override the endpoints (e.g. a runtime assets/config.json).
export const environment = {
  production: true,
  otelServiceName: 'angular-browser',
  deploymentEnvironment: 'development',
  otelCollectorUrl: 'http://localhost:4318',
  apiBaseUrl: 'http://localhost:3000/api',
  // Only attach `traceparent` to our own API (don't leak trace headers cross-site).
  apiTraceUrls: [/^http:\/\/localhost:3000/] as RegExp[],
};
