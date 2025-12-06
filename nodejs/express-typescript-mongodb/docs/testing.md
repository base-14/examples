# Testing Guide

## Quick Commands

```bash
npm test                 # All tests
npm run test:unit        # Unit only
npm run test:integration # Integration only
npm run test:e2e         # E2E only
npm run test:coverage    # With coverage

./scripts/test-api.sh    # API smoke test (17 scenarios)
```

## Test Structure

```text
tests/
├── unit/              # Isolated function tests
├── integration/       # API endpoint tests
└── e2e/               # Full workflow tests
```

## Writing Tests

**Unit test (isolated functions)**:

```typescript
it('should strip XSS tags', () => {
  const result = sanitizeHtml('<script>bad</script>ok');
  expect(result).toBe('ok');
});
```

**Integration test (API endpoints)**:

```typescript
it('should create article', async () => {
  const res = await request(app)
    .post('/api/v1/articles')
    .set('Authorization', `Bearer ${token}`)
    .send({ title: 'Test', content: 'Content' })
    .expect(201);

  expect(res.body.title).toBe('Test');
});
```

**Test failure scenarios**:

```typescript
it('should reject empty title', async () => {
  await request(app)
    .post('/api/v1/articles')
    .set('Authorization', `Bearer ${token}`)
    .send({ title: '', content: 'Content' })
    .expect(400);
});
```

## Coverage

Current: **66.72%** | Target: **>70%**

```bash
npm run test:coverage
```

## Debugging

```bash
npx vitest tests/unit/utils/sanitize.test.ts  # Single file
npx vitest --watch                             # Watch mode
```
