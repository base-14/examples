export default function Home() {
  return (
    <main style={{ padding: '2rem', fontFamily: 'system-ui, sans-serif' }}>
      <h1>Next.js API with MongoDB</h1>
      <p>API endpoints available:</p>
      <ul>
        <li>
          <code>GET /api/health</code> - Health check
        </li>
        <li>
          <code>POST /api/auth/register</code> - User registration
        </li>
        <li>
          <code>POST /api/auth/login</code> - User login
        </li>
        <li>
          <code>GET /api/articles</code> - List articles
        </li>
        <li>
          <code>POST /api/articles</code> - Create article
        </li>
      </ul>
    </main>
  );
}
