import {
  Controller,
  Post,
  Delete,
  Param,
  UseGuards,
  ParseUUIDPipe,
} from '@nestjs/common';
import { FavoritesService } from './favorites.service';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { User } from '../users/entities/user.entity';

@Controller('api/articles')
export class FavoritesController {
  constructor(private favoritesService: FavoritesService) {}

  @Post(':id/favorite')
  @UseGuards(JwtAuthGuard)
  favorite(@Param('id', ParseUUIDPipe) id: string, @CurrentUser() user: User) {
    return this.favoritesService.favorite(id, user.id);
  }

  @Delete(':id/favorite')
  @UseGuards(JwtAuthGuard)
  unfavorite(
    @Param('id', ParseUUIDPipe) id: string,
    @CurrentUser() user: User,
  ) {
    return this.favoritesService.unfavorite(id, user.id);
  }
}
