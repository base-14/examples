import { Module, forwardRef } from '@nestjs/common';
import { BullModule } from '@nestjs/bullmq';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { NotificationProcessor } from './notification.processor';
import { NotificationService } from './notification.service';
import { JobMetricsService } from './job-metrics.service';
import { Article } from '../articles/entities/article.entity';
import { EventsModule } from '../events/events.module';

@Module({
  imports: [
    BullModule.forRootAsync({
      imports: [ConfigModule],
      useFactory: (configService: ConfigService) => ({
        connection: {
          url: configService.get<string>('redis.url'),
        },
      }),
      inject: [ConfigService],
    }),
    BullModule.registerQueue({
      name: 'notifications',
    }),
    TypeOrmModule.forFeature([Article]),
    forwardRef(() => EventsModule),
  ],
  providers: [NotificationProcessor, NotificationService, JobMetricsService],
  exports: [NotificationService, JobMetricsService],
})
export class JobsModule {}
