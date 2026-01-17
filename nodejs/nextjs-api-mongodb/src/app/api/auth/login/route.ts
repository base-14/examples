import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { connectDB } from '@/lib/db';
import { User } from '@/models/User';
import { signToken } from '@/lib/auth';
import { ValidationError, AuthenticationError } from '@/lib/errors';
import { formatZodErrors } from '@/lib/validators';
import { withSpan } from '@/lib/telemetry';
import { logger, logError } from '@/lib/logger';
import { recordAuth } from '@/lib/metrics';
import { checkRateLimit, getRateLimitKey, AUTH_RATE_LIMIT } from '@/lib/ratelimit';
import type { ApiResponse } from '@/types';

const loginSchema = z.object({
  email: z.string().email('Invalid email format'),
  password: z.string().min(1, 'Password is required'),
});

interface LoginResponse {
  user: {
    id: string;
    email: string;
    username: string;
  };
  token: string;
}

export async function POST(
  request: NextRequest
): Promise<NextResponse<ApiResponse<LoginResponse>>> {
  return withSpan('auth.login', async () => {
    try {
      const ip = request.headers.get('x-forwarded-for') || request.headers.get('x-real-ip');
      const rateLimitKey = getRateLimitKey(ip, 'auth:login');
      const rateLimit = await checkRateLimit(
        rateLimitKey,
        AUTH_RATE_LIMIT.limit,
        AUTH_RATE_LIMIT.windowMs
      );

      if (!rateLimit.success) {
        recordAuth('login', false);
        return NextResponse.json(
          {
            success: false,
            error: 'Too many login attempts. Please try again later.',
          },
          {
            status: 429,
            headers: {
              'Retry-After': String(rateLimit.reset),
              'X-RateLimit-Remaining': '0',
              'X-RateLimit-Reset': String(rateLimit.reset),
            },
          }
        );
      }

      await connectDB();

      const body = await request.json();
      const validation = loginSchema.safeParse(body);

      if (!validation.success) {
        const errors = formatZodErrors(validation.error);
        throw new ValidationError('Validation failed', errors);
      }

      const { email, password } = validation.data;

      const user = await User.findOne({ email: email.toLowerCase() }).select(
        '+password'
      );

      if (!user) {
        throw new AuthenticationError('Invalid email or password');
      }

      const isValidPassword = await user.comparePassword(password);
      if (!isValidPassword) {
        throw new AuthenticationError('Invalid email or password');
      }

      const token = signToken({
        userId: user._id.toString(),
        email: user.email,
      });

      recordAuth('login', true);
      logger.info('User logged in', { userId: user._id.toString(), username: user.username });
      return NextResponse.json({
        success: true,
        data: {
          user: {
            id: user._id.toString(),
            email: user.email,
            username: user.username,
          },
          token,
        },
      });
    } catch (error) {
      recordAuth('login', false);
      if (error instanceof ValidationError) {
        return NextResponse.json(
          { success: false, error: error.message, details: error.details },
          { status: error.statusCode }
        );
      }
      if (error instanceof AuthenticationError) {
        return NextResponse.json(
          { success: false, error: error.message },
          { status: error.statusCode }
        );
      }
      logError('Login failed', error, { operation: 'auth.login' });
      return NextResponse.json(
        { success: false, error: 'Login failed' },
        { status: 500 }
      );
    }
  });
}
