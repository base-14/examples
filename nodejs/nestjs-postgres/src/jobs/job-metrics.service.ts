import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { InjectQueue } from '@nestjs/bullmq';
import { Queue } from 'bullmq';
import { metrics } from '@opentelemetry/api';

const meter = metrics.getMeter('job-queue-metrics');

@Injectable()
export class JobMetricsService implements OnModuleInit, OnModuleDestroy {
  private observableInterval: NodeJS.Timeout | null = null;

  private readonly queueWaitingGauge = meter.createObservableGauge(
    'job_queue_waiting',
    {
      description: 'Number of jobs waiting in the queue',
    },
  );

  private readonly queueActiveGauge = meter.createObservableGauge(
    'job_queue_active',
    {
      description: 'Number of jobs currently being processed',
    },
  );

  private readonly queueDelayedGauge = meter.createObservableGauge(
    'job_queue_delayed',
    {
      description: 'Number of delayed jobs in the queue',
    },
  );

  private readonly queueFailedGauge = meter.createObservableGauge(
    'job_queue_failed',
    {
      description: 'Number of failed jobs in the queue',
    },
  );

  private readonly queueCompletedGauge = meter.createObservableGauge(
    'job_queue_completed',
    {
      description: 'Number of completed jobs (last 24h)',
    },
  );

  private queueStats = {
    waiting: 0,
    active: 0,
    delayed: 0,
    failed: 0,
    completed: 0,
  };

  constructor(
    @InjectQueue('notifications') private notificationsQueue: Queue,
  ) {}

  onModuleInit() {
    this.queueWaitingGauge.addCallback((observableResult) => {
      observableResult.observe(this.queueStats.waiting, {
        queue: 'notifications',
      });
    });

    this.queueActiveGauge.addCallback((observableResult) => {
      observableResult.observe(this.queueStats.active, {
        queue: 'notifications',
      });
    });

    this.queueDelayedGauge.addCallback((observableResult) => {
      observableResult.observe(this.queueStats.delayed, {
        queue: 'notifications',
      });
    });

    this.queueFailedGauge.addCallback((observableResult) => {
      observableResult.observe(this.queueStats.failed, {
        queue: 'notifications',
      });
    });

    this.queueCompletedGauge.addCallback((observableResult) => {
      observableResult.observe(this.queueStats.completed, {
        queue: 'notifications',
      });
    });

    this.observableInterval = setInterval(() => {
      this.updateQueueStats().catch(console.error);
    }, 5000);

    this.updateQueueStats().catch(console.error);
  }

  onModuleDestroy() {
    if (this.observableInterval) {
      clearInterval(this.observableInterval);
    }
  }

  private async updateQueueStats() {
    const [waiting, active, delayed, failed, completed] = await Promise.all([
      this.notificationsQueue.getWaitingCount(),
      this.notificationsQueue.getActiveCount(),
      this.notificationsQueue.getDelayedCount(),
      this.notificationsQueue.getFailedCount(),
      this.notificationsQueue.getCompletedCount(),
    ]);

    this.queueStats = { waiting, active, delayed, failed, completed };
  }

  async getQueueStats() {
    await this.updateQueueStats();
    return this.queueStats;
  }
}
