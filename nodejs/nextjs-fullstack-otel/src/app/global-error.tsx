'use client';

import { useEffect } from 'react';
import { reportErrorBoundary } from '@/lib/browser-telemetry';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    reportErrorBoundary(error);
  }, [error]);

  return (
    <html>
      <body className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="border border-red-300 bg-red-50 rounded-lg p-8 max-w-md">
          <h2 className="text-xl font-bold text-red-800 mb-2">Something went wrong</h2>
          <p className="text-sm text-red-600 mb-4">{error.message}</p>
          <button
            onClick={reset}
            className="bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
          >
            Try Again
          </button>
        </div>
      </body>
    </html>
  );
}
