import {
  ApplicationConfig,
  ErrorHandler,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';

import { routes } from './app.routes';
import { TelemetryErrorHandler } from './telemetry/error-handler';
import { errorLogInterceptor } from './telemetry/error-interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    { provide: ErrorHandler, useClass: TelemetryErrorHandler },
    provideRouter(routes),
    // Fetch backend is the v22 default (OTel fetch instrumentation captures it +
    // attaches traceparent); interceptor emits a correlated log on failure.
    provideHttpClient(withInterceptors([errorLogInterceptor])),
  ],
};
