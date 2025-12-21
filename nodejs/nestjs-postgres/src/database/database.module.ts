import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ConfigService } from '@nestjs/config';

@Module({
  imports: [
    TypeOrmModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (configService: ConfigService) => ({
        type: 'postgres',
        url: configService.get<string>('database.url'),
        autoLoadEntities: true,
        synchronize: configService.get<string>('app.env') === 'development',
        logging: configService.get<string>('app.env') === 'development',
      }),
    }),
  ],
})
export class DatabaseModule {}
