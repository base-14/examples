export class ArticleResponseDto {
  id: string;
  title: string;
  content: string;
  tags: string[];
  published: boolean;
  publishedAt: Date | null;
  favoritesCount: number;
  authorId: string;
  createdAt: Date;
  updatedAt: Date;
}

export class PaginationMeta {
  page: number;
  limit: number;
  total: number;
  totalPages: number;
}

export class PaginatedArticlesResponseDto {
  data: ArticleResponseDto[];
  meta: PaginationMeta;
}

export class PublishJobResponseDto {
  message: string;
  jobId?: string;
  statusUrl?: string;
}
