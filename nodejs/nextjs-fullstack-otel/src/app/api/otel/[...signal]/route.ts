import { NextRequest, NextResponse } from 'next/server';

// Proxy browser OTel data to the collector — avoids CORS configuration.
// Browser SDK sends to /api/otel/v1/traces (or /v1/metrics, /v1/logs)
// and this route forwards it to the collector's OTLP HTTP endpoint.

const COLLECTOR_ENDPOINT = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ signal: string[] }> }
) {
  const { signal } = await params;
  const path = signal.join('/'); // e.g. "v1/traces" or "v1/metrics" or "v1/logs"

  const body = await request.arrayBuffer();

  const collectorUrl = `${COLLECTOR_ENDPOINT}/${path}`;

  const response = await fetch(collectorUrl, {
    method: 'POST',
    headers: {
      'Content-Type': request.headers.get('Content-Type') || 'application/json',
    },
    body,
  });

  return new NextResponse(response.body, {
    status: response.status,
    headers: {
      'Content-Type': response.headers.get('Content-Type') || 'application/json',
    },
  });
}
