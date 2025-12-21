import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  ManyToOne,
  JoinColumn,
  Unique,
} from 'typeorm';
import { User } from '../../users/entities/user.entity';
import { Article } from '../../articles/entities/article.entity';

@Entity('favorites')
@Unique(['userId', 'articleId'])
export class Favorite {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @ManyToOne(() => User)
  @JoinColumn({ name: 'userId' })
  user: User;

  @Column()
  userId: string;

  @ManyToOne(() => Article)
  @JoinColumn({ name: 'articleId' })
  article: Article;

  @Column()
  articleId: string;

  @CreateDateColumn()
  createdAt: Date;
}
