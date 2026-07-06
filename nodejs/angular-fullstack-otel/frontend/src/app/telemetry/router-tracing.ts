import { Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { trace } from '@opentelemetry/api';

// The OTel web auto-instrumentations cover document-load, fetch/XHR, and user
// interactions, but not Angular's client-side Router. Subscribe to NavigationEnd
// so each SPA route change shows up as its own span.
export function initRouterTracing(router: Router): void {
  const tracer = trace.getTracer('angular-router');
  router.events
    .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
    .subscribe((e) => {
      const span = tracer.startSpan('router.navigation');
      span.setAttributes({
        'route.path': e.urlAfterRedirects,
        'nav.id': e.id,
        'page.url': window.location.href,
      });
      span.end();
    });
}
