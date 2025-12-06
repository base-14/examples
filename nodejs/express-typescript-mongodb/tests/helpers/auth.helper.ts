import { generateToken } from '../../src/utils/jwt';
import { User, type IUser } from '../../src/models/User';

export async function createTestUser(overrides?: Partial<IUser>): Promise<IUser> {
  const user = await User.create({
    email: overrides?.email || 'test@example.com',
    password: overrides?.password || 'password123',
    name: overrides?.name || 'Test User',
    role: overrides?.role || 'user',
  });
  return user;
}

export function createTestToken(userId: string, email: string, role: string = 'user'): string {
  return generateToken({ userId, email, role });
}

export async function createAuthenticatedUser(): Promise<{ user: IUser; token: string }> {
  const user = await createTestUser();
  const token = createTestToken(user._id.toString(), user.email, user.role);
  return { user, token };
}
