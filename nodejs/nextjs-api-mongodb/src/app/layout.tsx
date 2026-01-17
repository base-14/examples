import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Next.js API with MongoDB',
  description: 'A production-ready Next.js API with MongoDB, authentication, and OpenTelemetry',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
