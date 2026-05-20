import { NextResponse } from 'next/server';
import { logError } from '@/lib/logger';

export async function GET() {
  // Intentional server-side error — demonstrates error capture in traces
  logError('Intentional server error triggered', { 'error.route': '/api/error', 'error.method': 'GET' });
  throw new Error('Intentional server error for OTel demo');
}

export async function POST() {
  // Return a 500 with a JSON body — demonstrates HTTP error status in spans
  logError('Server error response', { 'error.route': '/api/error', 'error.method': 'POST', 'http.status_code': 500 });
  return NextResponse.json(
    { error: 'Something went wrong on the server' },
    { status: 500 }
  );
}
