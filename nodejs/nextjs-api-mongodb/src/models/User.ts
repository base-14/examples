import mongoose, { Schema, Document, Model } from 'mongoose';
import bcrypt from 'bcrypt';

export interface IUser {
  email: string;
  username: string;
  password: string;
  bio?: string;
  image?: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface IUserDocument extends IUser, Document {
  comparePassword(candidatePassword: string): Promise<boolean>;
}

export interface IUserModel extends Model<IUserDocument> {
  findByEmail(email: string): Promise<IUserDocument | null>;
}

const userSchema = new Schema<IUserDocument, IUserModel>(
  {
    email: {
      type: String,
      required: [true, 'Email is required'],
      unique: true,
      lowercase: true,
      trim: true,
      index: true,
    },
    username: {
      type: String,
      required: [true, 'Username is required'],
      unique: true,
      trim: true,
      minlength: [3, 'Username must be at least 3 characters'],
      maxlength: [30, 'Username must be at most 30 characters'],
      index: true,
    },
    password: {
      type: String,
      required: [true, 'Password is required'],
      minlength: [8, 'Password must be at least 8 characters'],
      select: false,
    },
    bio: {
      type: String,
      maxlength: [500, 'Bio must be at most 500 characters'],
      default: '',
    },
    image: {
      type: String,
      default: '',
    },
  },
  {
    timestamps: true,
  }
);

// Mongoose 9: Use async pre hook without next() callback
userSchema.pre('save', async function () {
  if (!this.isModified('password')) {
    return;
  }
  const salt = await bcrypt.genSalt(12);
  this.password = await bcrypt.hash(this.password, salt);
});

userSchema.methods.comparePassword = async function (
  candidatePassword: string
): Promise<boolean> {
  return bcrypt.compare(candidatePassword, this.password);
};

userSchema.statics.findByEmail = function (
  email: string
): Promise<IUserDocument | null> {
  return this.findOne({ email: email.toLowerCase() });
};

userSchema.set('toJSON', {
  transform: (_doc, ret) => {
    const { password: _password, __v: _v, ...rest } = ret;
    return rest;
  },
});

export const User: IUserModel =
  (mongoose.models.User as IUserModel) ||
  mongoose.model<IUserDocument, IUserModel>('User', userSchema);
