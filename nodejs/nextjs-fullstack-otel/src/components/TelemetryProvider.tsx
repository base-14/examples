'use client';

import { useEffect } from 'react';
import { initBrowserTelemetry } from '@/lib/browser-telemetry';

export default function TelemetryProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    initBrowserTelemetry();
  }, []);

  return <>{children}</>;
}
