// Development config (used by `ng serve`, the default dev configuration).
export const environment = {
  production: false,
  otelServiceName: 'angular-browser',
  deploymentEnvironment: 'development',
  otelCollectorUrl: 'http://localhost:4318',
  apiBaseUrl: 'http://localhost:3000/api',
  apiTraceUrls: [/^http:\/\/localhost:3000/] as RegExp[],
};
