import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
import { initBrowserTelemetry } from './app/telemetry/browser-telemetry';

initBrowserTelemetry();

bootstrapApplication(App, appConfig)
  .catch((err) => console.error(err));
