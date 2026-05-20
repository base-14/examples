'use client';

import { useState } from 'react';

// Component that crashes on render — triggers React error boundary
function CrashingComponent() {
  throw new Error('React component crash! This triggers the error boundary.');
  return null;
}

export default function ErrorDemoPage() {
  const [showCrash, setShowCrash] = useState(false);
  const [apiResult, setApiResult] = useState<string | null>(null);

  // 1. Trigger a plain JS error (caught by window.onerror)
  function triggerJsError() {
    // This will be caught by our window.addEventListener('error') handler
    // and reported as a browser.error span
    const obj: Record<string, unknown> = {};
    // @ts-expect-error intentional error for demo
    obj.nonExistent.property;
  }

  // 2. Trigger an unhandled promise rejection
  function triggerUnhandledRejection() {
    // This will be caught by our window.addEventListener('unhandledrejection') handler
    // and reported as a browser.unhandled_rejection span
    Promise.reject(new Error('Unhandled promise rejection for OTel demo'));
  }

  // 3. Trigger React error boundary (component crash)
  function triggerReactCrash() {
    setShowCrash(true);
  }

  // 4. Call a server API that returns 500
  async function triggerServerError() {
    setApiResult('Calling /api/error ...');
    try {
      const res = await fetch('/api/error', { method: 'POST' });
      const data = await res.json();
      setApiResult(`Server responded: ${res.status} — ${JSON.stringify(data)}`);
    } catch (err) {
      setApiResult(`Fetch error: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Error Demo</h1>
      <p className="mb-6 text-sm text-gray-500">
        Trigger different error types and check Jaeger to see how each one is captured.
        Look for the <code className="bg-gray-100 px-1 rounded">sample-nextjs-app-browser</code> service.
      </p>

      <div className="space-y-4">
        {/* JS Error */}
        <div className="border rounded-lg p-4 bg-white">
          <h2 className="font-semibold mb-1">1. JavaScript Error</h2>
          <p className="text-sm text-gray-500 mb-3">
            Throws a TypeError in a click handler. Caught by <code>window.onerror</code> and
            reported as a <code>browser.error</code> span.
          </p>
          <button
            onClick={triggerJsError}
            className="bg-red-600 text-white px-4 py-1.5 rounded text-sm hover:bg-red-700"
          >
            Trigger JS Error
          </button>
        </div>

        {/* Unhandled Rejection */}
        <div className="border rounded-lg p-4 bg-white">
          <h2 className="font-semibold mb-1">2. Unhandled Promise Rejection</h2>
          <p className="text-sm text-gray-500 mb-3">
            Creates a rejected promise with no catch handler. Caught by{' '}
            <code>window.onunhandledrejection</code> and reported as a{' '}
            <code>browser.unhandled_rejection</code> span.
          </p>
          <button
            onClick={triggerUnhandledRejection}
            className="bg-orange-600 text-white px-4 py-1.5 rounded text-sm hover:bg-orange-700"
          >
            Trigger Unhandled Rejection
          </button>
        </div>

        {/* React Crash */}
        <div className="border rounded-lg p-4 bg-white">
          <h2 className="font-semibold mb-1">3. React Component Crash</h2>
          <p className="text-sm text-gray-500 mb-3">
            Renders a component that throws during render. Caught by the Next.js error boundary
            (<code>error.tsx</code>) and reported as a <code>browser.react_error_boundary</code> span.
          </p>
          <button
            onClick={triggerReactCrash}
            className="bg-purple-600 text-white px-4 py-1.5 rounded text-sm hover:bg-purple-700"
          >
            Trigger React Crash
          </button>
          {showCrash && <CrashingComponent />}
        </div>

        {/* Server Error */}
        <div className="border rounded-lg p-4 bg-white">
          <h2 className="font-semibold mb-1">4. Server API Error (500)</h2>
          <p className="text-sm text-gray-500 mb-3">
            Calls <code>POST /api/error</code> which returns a 500. Visible in Jaeger as both a
            browser-side fetch span and a server-side API route span with error status.
          </p>
          <button
            onClick={triggerServerError}
            className="bg-gray-800 text-white px-4 py-1.5 rounded text-sm hover:bg-gray-900"
          >
            Trigger Server Error
          </button>
          {apiResult && <p className="mt-2 text-sm text-gray-600 font-mono">{apiResult}</p>}
        </div>
      </div>
    </div>
  );
}
