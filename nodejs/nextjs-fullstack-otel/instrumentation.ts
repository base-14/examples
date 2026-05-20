export async function register() {
  // Only load server-side OTel in the Node.js runtime (not Edge)
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    await import('./src/lib/server-telemetry');
  }
}
