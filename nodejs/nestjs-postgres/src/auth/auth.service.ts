import {
  Injectable,
  UnauthorizedException,
  ConflictException,
} from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcrypt';
import { trace, SpanStatusCode, metrics } from '@opentelemetry/api';
import { UsersService } from '../users/users.service';
import { RegisterDto } from './dto/register.dto';
import { LoginDto } from './dto/login.dto';
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

type UserWithoutPassword = Omit<User, 'password'>;

function excludePassword(user: User): UserWithoutPassword {
  const { id, email, name, role, createdAt, updatedAt } = user;
  return { id, email, name, role, createdAt, updatedAt };
}

@Injectable()
export class AuthService {
  constructor(
    private usersService: UsersService,
    private jwtService: JwtService,
  ) {}

  async register(
    dto: RegisterDto,
  ): Promise<{ user: UserWithoutPassword; token: string }> {
    return tracer.startActiveSpan('auth.register', async (span) => {
      try {
        span.setAttributes({
          'user.email': dto.email,
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

        const token = this.generateToken(user);
        span.setStatus({ code: SpanStatusCode.OK });
        return { user: excludePassword(user), token };
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

  async login(
    dto: LoginDto,
  ): Promise<{ user: UserWithoutPassword; token: string }> {
    return tracer.startActiveSpan('auth.login', async (span) => {
      try {
        span.setAttribute('user.email', dto.email);
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

        const token = this.generateToken(user);
        span.setStatus({ code: SpanStatusCode.OK });
        return { user: excludePassword(user), token };
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

  async getProfile(userId: string): Promise<UserWithoutPassword> {
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
        return excludePassword(user);
      } catch (error) {
        span.setStatus({ code: SpanStatusCode.ERROR, message: String(error) });
        throw error;
      } finally {
        span.end();
      }
    });
  }

  private generateToken(user: User): string {
    return this.jwtService.sign({
      sub: user.id,
      email: user.email,
    });
  }
}
