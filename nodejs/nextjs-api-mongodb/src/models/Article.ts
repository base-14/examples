import mongoose, { Schema, Document, Model, Types } from 'mongoose';

export interface IArticle {
  slug: string;
  title: string;
  description: string;
  body: string;
  tags: string[];
  authorId: Types.ObjectId;
  favoritesCount: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface IArticleDocument extends IArticle, Document {}

export interface IArticleModel extends Model<IArticleDocument> {
  findBySlug(slug: string): Promise<IArticleDocument | null>;
}

function slugify(title: string): string {
  return title
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/[\s_-]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

const articleSchema = new Schema<IArticleDocument, IArticleModel>(
  {
    slug: {
      type: String,
      required: true,
      unique: true,
      lowercase: true,
      index: true,
    },
    title: {
      type: String,
      required: [true, 'Title is required'],
      trim: true,
      minlength: [1, 'Title cannot be empty'],
      maxlength: [200, 'Title must be at most 200 characters'],
    },
    description: {
      type: String,
      required: [true, 'Description is required'],
      trim: true,
      maxlength: [500, 'Description must be at most 500 characters'],
    },
    body: {
      type: String,
      required: [true, 'Body is required'],
    },
    tags: {
      type: [String],
      default: [],
      index: true,
    },
    authorId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
      index: true,
    },
    favoritesCount: {
      type: Number,
      default: 0,
      min: 0,
    },
  },
  {
    timestamps: true,
  }
);

articleSchema.index({ createdAt: -1 });
articleSchema.index({ authorId: 1, createdAt: -1 });

// Mongoose 9: Use async pre hook without next() callback
articleSchema.pre('validate', async function () {
  if (this.isModified('title') || this.isNew) {
    const baseSlug = slugify(this.title);
    let slug = baseSlug;
    let counter = 1;

    while (true) {
      const existing = await mongoose.models.Article.findOne({ slug });
      if (!existing || existing._id.equals(this._id)) {
        break;
      }
      slug = `${baseSlug}-${counter}`;
      counter++;
    }

    this.slug = slug;
  }
});

articleSchema.statics.findBySlug = function (
  slug: string
): Promise<IArticleDocument | null> {
  return this.findOne({ slug: slug.toLowerCase() });
};

articleSchema.set('toJSON', {
  transform: (_doc, ret) => {
    const { __v: _v, ...rest } = ret;
    return rest;
  },
});

export const Article: IArticleModel =
  (mongoose.models.Article as IArticleModel) ||
  mongoose.model<IArticleDocument, IArticleModel>('Article', articleSchema);
