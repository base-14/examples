import mongoose, { Schema, Document, Model, Types } from 'mongoose';

export interface IFavorite {
  userId: Types.ObjectId;
  articleId: Types.ObjectId;
  createdAt: Date;
}

export interface IFavoriteDocument extends IFavorite, Document {}

export interface IFavoriteModel extends Model<IFavoriteDocument> {
  isFavorited(userId: string, articleId: string): Promise<boolean>;
  getFavoritedArticleIds(userId: string): Promise<string[]>;
}

const favoriteSchema = new Schema<IFavoriteDocument, IFavoriteModel>(
  {
    userId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
      index: true,
    },
    articleId: {
      type: Schema.Types.ObjectId,
      ref: 'Article',
      required: true,
      index: true,
    },
  },
  {
    timestamps: { createdAt: true, updatedAt: false },
  }
);

favoriteSchema.index({ userId: 1, articleId: 1 }, { unique: true });

favoriteSchema.statics.isFavorited = async function (
  userId: string,
  articleId: string
): Promise<boolean> {
  const favorite = await this.findOne({ userId, articleId });
  return !!favorite;
};

favoriteSchema.statics.getFavoritedArticleIds = async function (
  userId: string
): Promise<string[]> {
  const favorites = await this.find({ userId }).select('articleId');
  return favorites.map((f) => f.articleId.toString());
};

export const Favorite: IFavoriteModel =
  (mongoose.models.Favorite as IFavoriteModel) ||
  mongoose.model<IFavoriteDocument, IFavoriteModel>('Favorite', favoriteSchema);
