import mongoose, { Schema, type Document } from 'mongoose';

export interface IArticle extends Document {
  title: string;
  content: string;
  author: Schema.Types.ObjectId;
  tags: string[];
  published: boolean;
  publishedAt?: Date | undefined;
  viewCount: number;
  favoritesCount: number;
  createdAt: Date;
  updatedAt: Date;
}

const articleSchema = new Schema<IArticle>(
  {
    title: {
      type: String,
      required: true,
      trim: true,
      maxlength: 200,
    },
    content: {
      type: String,
      required: true,
      maxlength: 50000,
    },
    author: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    tags: {
      type: [String],
      default: [],
    },
    published: {
      type: Boolean,
      default: false,
    },
    publishedAt: {
      type: Date,
    },
    viewCount: {
      type: Number,
      default: 0,
    },
    favoritesCount: {
      type: Number,
      default: 0,
    },
  },
  {
    timestamps: true,
  }
);

articleSchema.index({ title: 'text' });
articleSchema.index({ author: 1 });
articleSchema.index({ published: 1, createdAt: -1 });
articleSchema.index({ author: 1, published: 1, createdAt: -1 });

export const Article = mongoose.model<IArticle>('Article', articleSchema);
