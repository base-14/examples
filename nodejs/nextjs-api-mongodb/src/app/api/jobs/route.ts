import { NextRequest, NextResponse } from 'next/server';
import { emailQueue, analyticsQueue, getQueueStats, addEmailJob, addAnalyticsJob } from '@/lib/queue';
import { getUserFromRequest } from '@/lib/auth';
import { withSpan } from '@/lib/telemetry';
import { logger, logError } from '@/lib/logger';
import type { ApiResponse } from '@/types';

export const dynamic = 'force-dynamic';

interface QueueStats {
  waiting: number;
  active: number;
  completed: number;
  failed: number;
}

interface JobsStatusResponse {
  email: QueueStats;
  analytics: QueueStats;
}

export async function GET(): Promise<NextResponse<ApiResponse<JobsStatusResponse>>> {
  return withSpan('jobs.status', async () => {
    try {
      const [emailStats, analyticsStats] = await Promise.all([
        getQueueStats(emailQueue),
        getQueueStats(analyticsQueue),
      ]);

      return NextResponse.json({
        success: true,
        data: {
          email: emailStats,
          analytics: analyticsStats,
        },
      });
    } catch (error) {
      logError('Failed to get jobs status', error, { operation: 'jobs.status' });
      return NextResponse.json(
        { success: false, error: 'Failed to get jobs status' },
        { status: 500 }
      );
    }
  });
}

interface JobTriggerResponse {
  jobId: string;
  type: string;
  status: string;
}

export async function POST(
  request: NextRequest
): Promise<NextResponse<ApiResponse<JobTriggerResponse>>> {
  try {
    getUserFromRequest(request);
  } catch {
    return NextResponse.json(
      { success: false, error: 'Authentication required' },
      { status: 401 }
    );
  }

  return withSpan('jobs.trigger', async () => {
    try {
      const body = await request.json();
      const { type, data } = body;

      if (type === 'email') {
        const job = await addEmailJob({
          to: data?.to || 'test@example.com',
          subject: data?.subject || 'Test Email',
          body: data?.body || 'This is a test email',
        });
        logger.info('Email job queued', { jobId: job.id, to: data?.to });
        return NextResponse.json({
          success: true,
          data: {
            jobId: job.id || 'unknown',
            type: 'email',
            status: 'queued',
          },
        });
      } else if (type === 'analytics') {
        const job = await addAnalyticsJob({
          event: data?.event || 'test_event',
          userId: data?.userId,
          data: data?.eventData || {},
          timestamp: new Date().toISOString(),
        });
        logger.info('Analytics job queued', { jobId: job.id, event: data?.event });
        return NextResponse.json({
          success: true,
          data: {
            jobId: job.id || 'unknown',
            type: 'analytics',
            status: 'queued',
          },
        });
      } else {
        logger.warn('Invalid job type requested', { type });
        return NextResponse.json(
          { success: false, error: 'Invalid job type. Use "email" or "analytics"' },
          { status: 400 }
        );
      }
    } catch (error) {
      logError('Failed to trigger job', error, { operation: 'jobs.trigger' });
      return NextResponse.json(
        { success: false, error: 'Failed to trigger job' },
        { status: 500 }
      );
    }
  });
}
