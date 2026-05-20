export default function Home() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Next.js OpenTelemetry Sample</h1>
      <p className="mb-6 text-gray-600">
        This sample app demonstrates full-stack OpenTelemetry instrumentation for Next.js,
        covering both server-side and browser-side telemetry.
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="border rounded-lg p-4 bg-white">
          <h2 className="font-semibold mb-2">Server-Side Telemetry</h2>
          <ul className="text-sm text-gray-600 space-y-1">
            <li>- HTTP request traces (auto)</li>
            <li>- SSR render spans (auto)</li>
            <li>- Server-side fetch tracing (auto)</li>
            <li>- API route execution spans (auto)</li>
            <li>- Structured OTel logs</li>
          </ul>
        </div>

        <div className="border rounded-lg p-4 bg-white">
          <h2 className="font-semibold mb-2">Browser-Side Telemetry</h2>
          <ul className="text-sm text-gray-600 space-y-1">
            <li>- Document load timing (auto)</li>
            <li>- Client-side fetch/XHR tracing (auto)</li>
            <li>- User interaction spans (clicks)</li>
            <li>- JS errors (window.onerror)</li>
            <li>- Unhandled promise rejections</li>
            <li>- React error boundary crashes</li>
            <li>- Core Web Vitals (LCP, CLS, INP, TTFB)</li>
          </ul>
        </div>
      </div>

      <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm">
        <strong>Try it:</strong> Navigate to{' '}
        <a href="/products" className="text-blue-600 underline">Products</a> to see server + client
        fetch traces, or <a href="/error-demo" className="text-blue-600 underline">Error Demo</a> to
        trigger various error types and see them in Jaeger.
      </div>
    </div>
  );
}
