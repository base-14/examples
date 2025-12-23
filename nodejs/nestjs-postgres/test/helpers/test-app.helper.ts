import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ThrottlerModule } from '@nestjs/throttler';
import { BullModule } from '@nestjs/bullmq';
import { AuthModule } from '../../src/auth/auth.module';
import { ArticlesModule } from '../../src/articles/articles.module';
import { FavoritesModule } from '../../src/favorites/favorites.module';
import { HealthModule } from '../../src/health/health.module';
import { JobsModule } from '../../src/jobs/jobs.module';
import { User } from '../../src/users/entities/user.entity';
import { Article } from '../../src/articles/entities/article.entity';
import { Favorite } from '../../src/favorites/entities/favorite.entity';

export interface TestAppInstance {
  app: INestApplication;
  module: TestingModule;
}

export async function createTestApp(): Promise<TestAppInstance> {
  const moduleFixture: TestingModule = await Test.createTestingModule({
    imports: [
      ConfigModule.forRoot({
        isGlobal: true,
        load: [
          () => ({
            app: {
              port: 3001,
              env: 'test',
              version: '1.0.0',
            },
            database: {
              url:
                process.env.DATABASE_URL ||
                'postgresql://postgres:postgres@localhost:5433/nestjs_test',
            },
            redis: {
              url: process.env.TEST_REDIS_URL || 'redis://localhost:6379',
            },
            jwt: {
              secret: 'test-secret-key',
              expiresIn: '1h',
            },
            cors: {
              origin: '*',
            },
            rateLimit: {
              windowMs: 900000,
              max: 1000,
            },
            otel: {
              serviceName: 'nestjs-test',
              endpoint: 'http://localhost:4318',
            },
          }),
        ],
      }),
      TypeOrmModule.forRootAsync({
        inject: [ConfigService],
        useFactory: (configService: ConfigService) => ({
          type: 'postgres',
          url: configService.get<string>('database.url'),
          entities: [User, Article, Favorite],
          synchronize: true,
          dropSchema: true,
        }),
      }),
      BullModule.forRootAsync({
        inject: [ConfigService],
        useFactory: (configService: ConfigService) => ({
          connection: {
            url: configService.get<string>('redis.url'),
          },
        }),
      }),
      BullModule.registerQueue({
        name: 'notifications',
      }),
      ThrottlerModule.forRoot({
        throttlers: [{ ttl: 60000, limit: 1000 }],
      }),
      AuthModule,
      ArticlesModule,
      FavoritesModule,
      HealthModule,
      JobsModule,
    ],
  }).compile();

  const app = moduleFixture.createNestApplication();

  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      forbidNonWhitelisted: true,
      transform: true,
    }),
  );

  await app.init();

  return { app, module: moduleFixture };
}

export async function closeTestApp(testApp: TestAppInstance): Promise<void> {
  await testApp.app.close();
}
