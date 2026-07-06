import { Component, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { trace, SpanStatusCode } from '@opentelemetry/api';
import { environment } from '../../environments/environment';

interface Item {
  id: number;
  name: string;
  price: string;
}

@Component({
  selector: 'app-items',
  imports: [],
  templateUrl: './items.html',
  styleUrl: './items.css',
})
export class Items {
  private http = inject(HttpClient);
  items = signal<Item[]>([]);

  loadItems(): void {
    const tracer = trace.getTracer('angular-items');
    // startActiveSpan makes items.load the active parent; the fetch fired
    // synchronously on subscribe nests under it even without zone.js.
    tracer.startActiveSpan('items.load', (span) => {
      this.http.get<Item[]>(`${environment.apiBaseUrl}/items`).subscribe({
        next: (data) => {
          this.items.set(data);
          span.end();
        },
        error: (err) => {
          span.recordException(err);
          span.setStatus({ code: SpanStatusCode.ERROR });
          span.end();
        },
      });
    });
  }

  // Demo: failing request inside an active span -> interceptor emits a correlated log.
  triggerApiError(): void {
    const tracer = trace.getTracer('angular-items');
    tracer.startActiveSpan('items.load.missing', (span) => {
      this.http.get<Item[]>(`${environment.apiBaseUrl}/missing`).subscribe({
        next: () => span.end(),
        error: (err) => {
          span.recordException(err);
          span.setStatus({ code: SpanStatusCode.ERROR });
          span.end();
        },
      });
    });
  }

  // Demo: uncaught throw -> ErrorHandler emits a best-effort (uncorrelated) log.
  triggerError(): void {
    throw new Error('Demo: uncaught error from Items page');
  }
}
