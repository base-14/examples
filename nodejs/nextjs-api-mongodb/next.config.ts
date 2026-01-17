import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  output: 'standalone',
  serverExternalPackages: ['mongoose', 'bcrypt', 'pino', 'bullmq', 'ioredis'],
};

export default nextConfig;
