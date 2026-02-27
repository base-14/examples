import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'url';

export default defineConfig({
  test: {
    globals: false,
    environment: 'node',
    setupFiles: ['./tests/setup.ts'],

    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov', 'json-summary'],
      exclude: [
        'node_modules/**',
        'dist/**',
        'tests/**',
        '**/*.d.ts',
        '**/*.test.ts',
        '**/*.spec.ts',
        'src/index.ts',
        'src/telemetry.ts',
        'src/database.ts',
        'src/jobs/workers/**',
      ],
      include: ['src/**/*.ts'],
      thresholds: {
        lines: 65,
        functions: 60,
        branches: 60,
        statements: 65,
        perFile: true,
      },
      all: true,
      clean: true,
      reportsDirectory: './coverage',
    },

    testTimeout: 30000,
    hookTimeout: 30000,
    isolate: true,
    pool: 'forks',

    reporters: ['default', 'html', 'json'],
    outputFile: {
      html: './test-results/index.html',
      json: './test-results/results.json',
    },

    typecheck: {
      enabled: false,
      tsconfig: './tsconfig.json',
    },
  },

  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
});
