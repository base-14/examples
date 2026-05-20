'use client';

import { useState } from 'react';

export function ClientFetchButton() {
  const [result, setResult] = useState<string | null>(null);

  async function handleFetch() {
    setResult('Loading...');
    try {
      const res = await fetch('/api/products');
      const data = await res.json();
      setResult(`Fetched ${data.total} products from browser`);
    } catch (err) {
      setResult(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  return (
    <div>
      <button
        onClick={handleFetch}
        className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700"
      >
        Fetch Products (Client-Side)
      </button>
      {result && <p className="mt-2 text-sm text-gray-600">{result}</p>}
    </div>
  );
}
