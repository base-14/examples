import { NextResponse } from 'next/server';
import { withSpan } from '@/lib/telemetry';
import { logger } from '@/lib/logger';
import type { ApiResponse } from '@/types';

interface LogoutResponse {
  message: string;
}

export async function POST(): Promise<NextResponse<ApiResponse<LogoutResponse>>> {
  return withSpan('auth.logout', async () => {
    logger.info('User logout requested');

    return NextResponse.json({
      success: true,
      data: {
        message: 'Logged out successfully. Please discard your token.',
      },
    });
  });
}
