import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Favorite } from './entities/favorite.entity';
import { FavoritesController } from './favorites.controller';
import { FavoritesService } from './favorites.service';
import { ArticlesModule } from '../articles/articles.module';

@Module({
  imports: [TypeOrmModule.forFeature([Favorite]), ArticlesModule],
  controllers: [FavoritesController],
  providers: [FavoritesService],
})
export class FavoritesModule {}
