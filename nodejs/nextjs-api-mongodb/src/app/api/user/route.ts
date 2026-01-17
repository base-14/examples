import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { connectDB } from '@/lib/db';
import { User } from '@/models/User';
import { withAuth } from '@/lib/auth';
import { ValidationError, NotFoundError } from '@/lib/errors';
import { formatZodErrors } from '@/lib/validators';
import { withSpan } from '@/lib/telemetry';
import { logError } from '@/lib/logger';
import type { ApiResponse, JwtPayload } from '@/types';

interface UserProfile {
  id: string;
  email: string;
  username: string;
  bio: string;
  image: string;
  createdAt: string;
}

const updateUserSchema = z.object({
  username: z
    .string()
    .min(3, 'Username must be at least 3 characters')
    .max(30, 'Username must be at most 30 characters')
    .regex(
      /^[a-zA-Z0-9_-]+$/,
      'Username can only contain letters, numbers, underscores, and hyphens'
    )
    .optional(),
  bio: z.string().max(500, 'Bio must be at most 500 characters').optional(),
  image: z.string().url('Image must be a valid URL').optional(),
});

export const GET = withAuth<UserProfile>(
  async (
    _request: NextRequest,
    user: JwtPayload
  ): Promise<NextResponse<ApiResponse<UserProfile>>> => {
    return withSpan('user.getProfile', async () => {
      try {
        await connectDB();

        const userData = await User.findById(user.userId);
        if (!userData) {
          throw new NotFoundError('User');
        }

        return NextResponse.json({
          success: true,
          data: {
            id: userData._id.toString(),
            email: userData.email,
            username: userData.username,
            bio: userData.bio || '',
            image: userData.image || '',
            createdAt: userData.createdAt.toISOString(),
          },
        });
      } catch (error) {
        if (error instanceof NotFoundError) {
          return NextResponse.json(
            { success: false, error: error.message },
            { status: error.statusCode }
          );
        }
        logError('Failed to get user profile', error, { operation: 'user.getProfile' });
        return NextResponse.json(
          { success: false, error: 'Failed to get user profile' },
          { status: 500 }
        );
      }
    });
  }
);

export const PUT = withAuth<UserProfile>(
  async (
    request: NextRequest,
    user: JwtPayload
  ): Promise<NextResponse<ApiResponse<UserProfile>>> => {
    return withSpan('user.updateProfile', async () => {
      try {
        await connectDB();

        const body = await request.json();
        const validation = updateUserSchema.safeParse(body);

        if (!validation.success) {
          const errors = formatZodErrors(validation.error);
          throw new ValidationError('Validation failed', errors);
        }

        const updateData = validation.data;

        if (updateData.username) {
          const existingUser = await User.findOne({
            username: updateData.username,
            _id: { $ne: user.userId },
          });
          if (existingUser) {
            return NextResponse.json(
              { success: false, error: 'Username already taken' },
              { status: 409 }
            );
          }
        }

        const userData = await User.findByIdAndUpdate(
          user.userId,
          { $set: updateData },
          { new: true, runValidators: true }
        );

        if (!userData) {
          throw new NotFoundError('User');
        }

        return NextResponse.json({
          success: true,
          data: {
            id: userData._id.toString(),
            email: userData.email,
            username: userData.username,
            bio: userData.bio || '',
            image: userData.image || '',
            createdAt: userData.createdAt.toISOString(),
          },
        });
      } catch (error) {
        if (error instanceof ValidationError) {
          return NextResponse.json(
            { success: false, error: error.message, details: error.details },
            { status: error.statusCode }
          );
        }
        if (error instanceof NotFoundError) {
          return NextResponse.json(
            { success: false, error: error.message },
            { status: error.statusCode }
          );
        }
        logError('Failed to update user profile', error, { operation: 'user.updateProfile' });
        return NextResponse.json(
          { success: false, error: 'Failed to update user profile' },
          { status: 500 }
        );
      }
    });
  }
);
