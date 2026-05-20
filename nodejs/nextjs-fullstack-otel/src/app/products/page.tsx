interface Product {
  id: number;
  name: string;
  category: string;
  price: number;
}

// Server component — fetch happens server-side during SSR
// This generates an AppRender.fetch span on the server
async function getProducts(): Promise<{ products: Product[]; total: number }> {
  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000';
  const res = await fetch(`${baseUrl}/api/products`, { cache: 'no-store' });
  return res.json();
}

export default async function ProductsPage() {
  const { products } = await getProducts();

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Products</h1>
      <p className="mb-4 text-sm text-gray-500">
        This page fetches data server-side during SSR. Check Jaeger for the
        server-side fetch span and the render route span.
      </p>

      <div className="border rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead className="bg-gray-100">
            <tr>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-left px-4 py-2">Category</th>
              <th className="text-right px-4 py-2">Price (INR/MT)</th>
            </tr>
          </thead>
          <tbody>
            {products.map((product) => (
              <tr key={product.id} className="border-t">
                <td className="px-4 py-2">{product.name}</td>
                <td className="px-4 py-2 text-gray-600">{product.category}</td>
                <td className="px-4 py-2 text-right font-mono">
                  {product.price.toLocaleString('en-IN')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Client-side fetch button — triggers a browser-side fetch span */}
      <ClientFetchDemo />
    </div>
  );
}

// Separate client component for the client-side fetch demo
function ClientFetchDemo() {
  return (
    <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
      <p className="text-sm font-medium mb-2">Client-Side Fetch Demo</p>
      <p className="text-xs text-gray-500 mb-3">
        Click the button below to trigger a fetch from the browser.
        This generates a browser-side fetch span visible in Jaeger under the browser service.
      </p>
      <ClientFetchButton />
    </div>
  );
}

// Need 'use client' for the interactive button
import { ClientFetchButton } from './client-fetch-button';
