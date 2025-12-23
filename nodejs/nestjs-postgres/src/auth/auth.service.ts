import {
  Injectable,
  UnauthorizedException,
  ConflictException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcrypt';
import { trace, SpanStatusCode, metrics } from '@opentelemetry/api';
import { UsersService } from '../users/users.service';
import { RegisterDto } from './dto/register.dto';
import { LoginDto } from './dto/login.dto';
import { AuthResponseDto } from './dto/auth-response.dto';
import { UserResponseDto } from '../users/dto/user-response.dto';
import { User } from '../users/entities/user.entity';

const tracer = trace.getTracer('auth-service');
const meter = metrics.getMeter('auth-service');

const loginAttemptsCounter = meter.createCounter('auth.login.attempts', {
  description: 'Number of login attempts',
});

const loginSuccessCounter = meter.createCounter('auth.login.success', {
  description: 'Number of successful logins',
});

const registrationCounter = meter.createCounter('auth.registration.total', {
  description: 'Number of user registrations',
});

function toUserResponse(user: User): UserResponseDto {
  return {
    id: user.id,
    email: user.email,
    name: user.name,
    role: user.role,
    createdAt: user.createdAt,
    updatedAt: user.updatedAt,
  };
}

function parseExpiresIn(expiresIn: string): number {
  const match = expiresIn.match(/^(\d+)([smhd])$/);
  if (!match) return 7 * 24 * 60 * 60 * 1000;
  const value = parseInt(match[1], 10);
  const unit = match[2];
  const multipliers: Record<string, number> = {
    s: 1000,
    m: 60 * 1000,
    h: 60 * 60 * 1000,
    d: 24 * 60 * 60 * 1000,
  };
  return value * (multipliers[unit] || 1000);
}

@Injectable()
export class AuthService {
  private readonly expiresIn: string;

  constructor(
    private usersService: UsersService,
    private jwtService: JwtService,
    private configService: ConfigService,
  ) {
    this.expiresIn = this.configService.get<string>('jwt.expiresIn') || '7d';
  }

  async register(dto: RegisterDto): Promise<AuthResponseDto> {
    return tracer.startActiveSpan('auth.register', async (span) => {
      try {
        span.setAttributes({
          'user.email_domain': dto.email.split('@')[1],
          'user.name': dto.name,
        });

        const existingUser = await this.usersService.findByEmail(dto.email);
        if (existingUser) {
          span.setStatus({
            code: SpanStatusCode.ERROR,
            message: 'Email already exists',
          });
          throw new ConflictException('Email already registered');
        }

        const hashedPassword = await bcrypt.hash(dto.password, 10);
        const user = await this.usersService.create({
          email: dto.email,
          password: hashedPassword,
          name: dto.name,
        });

        span.setAttribute('user.id', user.id);
        registrationCounter.add(1, { status: 'success' });

        const authResponse = this.generateAuthResponse(user);
        span.setStatus({ code: SpanStatusCode.OK });
        return authResponse;
      } catch (error) {
        if (!(error instanceof ConflictException)) {
          span.setStatus({
            code: SpanStatusCode.ERROR,
            message: String(error),
          });
          registrationCounter.add(1, { status: 'error' });
        }
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async login(dto: LoginDto): Promise<AuthResponseDto> {
    return tracer.startActiveSpan('auth.login', async (span) => {
      try {
        span.setAttribute('user.email_domain', dto.email.split('@')[1]);
        loginAttemptsCounter.add(1);

        const user = await this.usersService.findByEmail(dto.email);
        if (!user) {
          span.setStatus({
            code: SpanStatusCode.ERROR,
            message: 'Invalid credentials',
          });
          throw new UnauthorizedException('Invalid credentials');
        }

        const isPasswordValid = await bcrypt.compare(
          dto.password,
          user.password,
        );
        if (!isPasswordValid) {
          span.setStatus({
            code: SpanStatusCode.ERROR,
            message: 'Invalid credentials',
          });
          throw new UnauthorizedException('Invalid credentials');
        }

        span.setAttribute('user.id', user.id);
        loginSuccessCounter.add(1);

        const authResponse = this.generateAuthResponse(user);
        span.setStatus({ code: SpanStatusCode.OK });
        return authResponse;
      } catch (error) {
        if (!(error instanceof UnauthorizedException)) {
          span.setStatus({
            code: SpanStatusCode.ERROR,
            message: String(error),
          });
        }
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async getProfile(userId: string): Promise<UserResponseDto> {
    return tracer.startActiveSpan('auth.getProfile', async (span) => {
      try {
        span.setAttribute('user.id', userId);

        const user = await this.usersService.findById(userId);
        if (!user) {
          span.setStatus({
            code: SpanStatusCode.ERROR,
            message: 'User not found',
          });
          throw new UnauthorizedException('User not found');
        }

        span.setStatus({ code: SpanStatusCode.OK });
        return toUserResponse(user);
      } catch (error) {
        span.setStatus({ code: SpanStatusCode.ERROR, message: String(error) });
        throw error;
      } finally {
        span.end();
      }
    });
  }

  private generateAuthResponse(user: User): AuthResponseDto {
    const token = this.jwtService.sign({
      sub: user.id,
      email: user.email,
    });

    return {
      user: toUserResponse(user),
      token,
      expiresIn: this.expiresIn,
      expiresAt: Date.now() + parseExpiresIn(this.expiresIn),
      tokenType: 'Bearer',
    };
  }
}
