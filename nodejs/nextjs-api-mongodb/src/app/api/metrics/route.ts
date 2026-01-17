import { NextResponse } from 'next/server';
import { IncomingMessage, ServerResponse } from 'http';
import { getPrometheusExporter } from '@/lib/telemetry';

export async function GET(): Promise<Response> {
  try {
    const exporter = getPrometheusExporter();

    return new Promise((resolve) => {
      const mockRes = {
        statusCode: 200,
        setHeader: () => mockRes,
        end: (data: string) => {
          resolve(
            new Response(data, {
              status: 200,
              headers: {
                'Content-Type': 'text/plain; charset=utf-8',
              },
            })
          );
        },
      } as unknown as ServerResponse;

      const mockReq = {} as IncomingMessage;

      exporter.getMetricsRequestHandler(mockReq, mockRes);
    });
  } catch (error) {
    console.error('Failed to get metrics:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to get metrics' },
      { status: 500 }
    );
  }
}
