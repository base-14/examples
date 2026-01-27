import { FastifyPluginAsync } from 'fastify';
import * as userService from '../services/user.js';
import { registerSchema, loginSchema, getUserSchema, updateUserSchema } from '../schemas/user.js';

interface RegisterBody {
  email: string;
  password: string;
  name: string;
}

interface LoginBody {
  email: string;
  password: string;
}

interface UpdateUserBody {
  name?: string;
  bio?: string;
  image?: string;
}

const authRateLimitConfig = {
  max: 5,
  timeWindow: '1 minute',
  keyGenerator: (request: { ip: string }) => request.ip,
};

const authRoutes: FastifyPluginAsync = async (fastify) => {
  fastify.post<{ Body: RegisterBody }>(
    '/register',
    {
      schema: registerSchema,
      config: { rateLimit: authRateLimitConfig },
    },
    async (request, reply) => {
      try {
        const { email, password, name } = request.body;
        const user = await userService.createUser({ email, password, name });
        const token = fastify.jwt.sign({ id: user.id, email: user.email });

        return reply.code(201).send({ user, token });
      } catch (error) {
        if ((error as Error).message === 'Email already exists') {
          return reply.code(409).send({
            error: 'Conflict',
            message: 'Email already exists',
          });
        }
        throw error;
      }
    }
  );

  fastify.post<{ Body: LoginBody }>(
    '/login',
    {
      schema: loginSchema,
      config: { rateLimit: authRateLimitConfig },
    },
    async (request, reply) => {
      try {
        const { email, password } = request.body;
        const user = await userService.validateCredentials(email, password);
        const token = fastify.jwt.sign({ id: user.id, email: user.email });

        return { user, token };
      } catch (error) {
        if ((error as Error).message === 'Invalid credentials') {
          return reply.code(401).send({
            error: 'Unauthorized',
            message: 'Invalid email or password',
          });
        }
        throw error;
      }
    }
  );

  fastify.get(
    '/user',
    {
      schema: getUserSchema,
      onRequest: [fastify.authenticate],
    },
    async (request, reply) => {
      const user = await userService.findById(request.user.id);

      if (!user) {
        return reply.code(404).send({
          error: 'Not Found',
          message: 'User not found',
        });
      }

      return { user };
    }
  );

  fastify.put<{ Body: UpdateUserBody }>(
    '/user',
    {
      schema: updateUserSchema,
      onRequest: [fastify.authenticate],
    },
    async (request, reply) => {
      const user = await userService.updateUser(request.user.id, request.body);

      if (!user) {
        return reply.code(404).send({
          error: 'Not Found',
          message: 'User not found',
        });
      }

      return { user };
    }
  );

  fastify.post(
    '/logout',
    {
      onRequest: [fastify.authenticate],
    },
    async (_request, reply) => {
      return reply.code(200).send({ message: 'Logged out successfully' });
    }
  );
};

export default authRoutes;
