import { NextResponse } from 'next/server';
import { logInfo } from '@/lib/logger';

const PRODUCTS = [
  { id: 1, name: 'HR Coil - E250A', category: 'Hot Rolled', price: 52000 },
  { id: 2, name: 'CR Sheet - DC01', category: 'Cold Rolled', price: 61000 },
  { id: 3, name: 'GI Coil - GP Grade', category: 'Galvanized', price: 67000 },
  { id: 4, name: 'SS Sheet - 304 2B', category: 'Stainless Steel', price: 185000 },
  { id: 5, name: 'TMT Bar - Fe500D', category: 'Rebars', price: 48000 },
];

export async function GET() {
  // Simulate some latency like a real DB/API call
  await new Promise((resolve) => setTimeout(resolve, 50));

  logInfo('Products fetched', { 'products.count': PRODUCTS.length });

  return NextResponse.json({
    products: PRODUCTS,
    total: PRODUCTS.length,
  });
}
