import type { IUser } from '../models/User.js';

declare global {
  namespace Express {
    interface Request {
      user?: IUser | undefined;
    }
  }
}

export {};
