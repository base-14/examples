import { NextResponse } from 'next/server';
import { connectDB } from '@/lib/db';
import { Article } from '@/models/Article';
import { withSpan } from '@/lib/telemetry';
import { logError } from '@/lib/logger';
import type { ApiResponse } from '@/types';

interface TagsResponse {
  tags: string[];
}

export async function GET(): Promise<NextResponse<ApiResponse<TagsResponse>>> {
  return withSpan('tags.list', async () => {
    try {
      await connectDB();

      const tags = await Article.distinct('tags');

      return NextResponse.json({
        success: true,
        data: { tags: tags.sort() },
      });
    } catch (error) {
      logError('Failed to list tags', error, { operation: 'tags.list' });
      return NextResponse.json(
        { success: false, error: 'Failed to list tags' },
        { status: 500 }
      );
    }
  });
}
