import mongoose, { Schema, Document, Model, Types } from 'mongoose';

export interface IComment {
  articleId: Types.ObjectId;
  authorId: Types.ObjectId;
  body: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface ICommentDocument extends IComment, Document {}

export interface ICommentModel extends Model<ICommentDocument> {
  findByArticle(articleId: Types.ObjectId | string): Promise<ICommentDocument[]>;
}

const commentSchema = new Schema<ICommentDocument, ICommentModel>(
  {
    articleId: {
      type: Schema.Types.ObjectId,
      ref: 'Article',
      required: true,
      index: true,
    },
    authorId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
      index: true,
    },
    body: {
      type: String,
      required: [true, 'Comment body is required'],
      minlength: [1, 'Comment cannot be empty'],
      maxlength: [10000, 'Comment must be at most 10000 characters'],
    },
  },
  {
    timestamps: true,
  }
);

commentSchema.index({ articleId: 1, createdAt: -1 });

commentSchema.statics.findByArticle = function (
  articleId: Types.ObjectId | string
): Promise<ICommentDocument[]> {
  return this.find({ articleId })
    .sort({ createdAt: -1 })
    .populate('authorId', 'username bio image');
};

commentSchema.set('toJSON', {
  transform: (_doc, ret) => {
    const { __v: _v, ...rest } = ret;
    return rest;
  },
});

export const Comment: ICommentModel =
  (mongoose.models.Comment as ICommentModel) ||
  mongoose.model<ICommentDocument, ICommentModel>('Comment', commentSchema);
