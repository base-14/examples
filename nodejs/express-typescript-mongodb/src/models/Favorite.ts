import mongoose, { Schema, type Document } from 'mongoose';

export interface IFavorite extends Document {
  user: Schema.Types.ObjectId;
  article: Schema.Types.ObjectId;
  createdAt: Date;
}

const favoriteSchema = new Schema<IFavorite>(
  {
    user: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    article: {
      type: Schema.Types.ObjectId,
      ref: 'Article',
      required: true,
    },
  },
  {
    timestamps: { createdAt: true, updatedAt: false },
  }
);

favoriteSchema.index({ user: 1, article: 1 }, { unique: true });
favoriteSchema.index({ article: 1 });

export const Favorite = mongoose.model<IFavorite>('Favorite', favoriteSchema);
