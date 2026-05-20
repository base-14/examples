'use client';

import { useEffect } from 'react';
import { reportErrorBoundary } from '@/lib/browser-telemetry';

export default function ErrorDemoError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Report this error boundary catch to OTel as a browser span
    reportErrorBoundary(error);
  }, [error]);

  return (
    <div className="border border-red-300 bg-red-50 rounded-lg p-6 mt-4">
      <h2 className="text-lg font-semibold text-red-800 mb-2">
        React Error Boundary Caught a Crash
      </h2>
      <p className="text-sm text-red-600 mb-1">
        <strong>Error:</strong> {error.message}
      </p>
      {error.digest && (
        <p className="text-xs text-gray-500 mb-3">Digest: {error.digest}</p>
      )}
      <p className="text-sm text-gray-600 mb-4">
        This error was reported to OpenTelemetry as a{' '}
        <code className="bg-red-100 px-1 rounded">browser.react_error_boundary</code> span.
        Check Jaeger to see it.
      </p>
      <button
        onClick={reset}
        className="bg-red-600 text-white px-4 py-1.5 rounded text-sm hover:bg-red-700"
      >
        Try Again
      </button>
    </div>
  );
}
