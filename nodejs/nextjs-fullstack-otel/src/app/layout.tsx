import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import TelemetryProvider from '@/components/TelemetryProvider';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'Next.js OTel Sample',
  description: 'Sample app demonstrating full OpenTelemetry instrumentation',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-gray-50 text-gray-900">
        <TelemetryProvider>
          <nav className="bg-white border-b border-gray-200 px-6 py-3">
            <div className="max-w-4xl mx-auto flex gap-6 items-center">
              <span className="font-semibold text-lg">OTel Demo</span>
              <a href="/" className="hover:text-blue-600">Home</a>
              <a href="/products" className="hover:text-blue-600">Products</a>
              <a href="/error-demo" className="hover:text-blue-600">Error Demo</a>
            </div>
          </nav>
          <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-8">
            {children}
          </main>
        </TelemetryProvider>
      </body>
    </html>
  );
}
