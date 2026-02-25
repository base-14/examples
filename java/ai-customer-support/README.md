# AI Customer Support

Conversational AI customer support agent with RAG retrieval, tool calling, intent classification, escalation routing, and full OpenTelemetry observability.

**Java 25 | Spring Boot 4.0.3 | Spring AI 2.0 | WebFlux | pgvector | OTel Java Agent**

## Architecture

```
Message → Classify → Retrieve → Generate → PII Scrub → Route
              │          │          │                      │
          gpt-4.1-mini  pgvector   gpt-4.1              Escalate?
          (fast)        (RAG)      (capable + tools)
```

5-stage pipeline with three-layer OTel: Java Agent (HTTP/DB/Spring auto-instrumentation), Spring AI built-in (ChatModel/VectorStore via Micrometer), and manual spans (pipeline stages, domain metrics, gateway contract).

## Quick Start

```bash
# Copy and configure environment
cp .env.example .env
# Set OPENAI_API_KEY in .env

# Start all services
docker compose up -d

# Run smoke tests
./scripts/test-api.sh

# Send a message
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What is the status of order ORD-10001?"}'
```

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/chat` | Send message, get JSON response with intent + content |
| `POST` | `/api/chat/stream` | Send message, get SSE streaming response |
| `GET` | `/api/conversations` | List all conversations |
| `GET` | `/api/conversations/{id}` | Get conversation with message history |
| `POST` | `/api/conversations/{id}/resolve` | Resolve a conversation |
| `GET` | `/api/products` | List all products |
| `GET` | `/api/products/{sku}` | Get product by SKU |
| `GET` | `/api/orders/{orderId}` | Get order by order ID |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/failures` | List failure scenarios (failure-injection profile) |
| `POST` | `/api/failures/{scenario}` | Trigger failure scenario |

## Data

TechMart e-commerce store: 50 KB articles (10 categories), 30 products, 20 customers, 25 orders, 10 returns. KB articles are embedded into pgvector on first startup via Spring AI's OpenAI embedding model (text-embedding-3-small).

## Tool Calling

Spring AI `@Tool`-annotated methods available to the LLM:

| Tool | Description |
| --- | --- |
| `getOrderStatus` | Look up order status by order ID |
| `getOrderHistory` | Get customer's recent orders by email |
| `initiateReturn` | Start a return for a delivered order |
| `getReturnStatus` | Check return status by return ID |
| `searchProducts` | Search catalog by name/category |
| `getProductInfo` | Get product details by SKU |

## Observability

Every message produces a trace with:
- `support_conversation` — root pipeline span
- `classify_intent` — intent classification (fast model)
- `rag_retrieval` — pgvector similarity search with match count
- `gen_ai.chat {model}` — LLM calls with full GenAI semconv attributes
- `generate_response` — response generation (capable model)
- `escalation_check` — escalation rule evaluation

GenAI metrics: token usage, operation duration, cost, retry count, fallback count, error count.
Domain metrics: conversation turns, conversation duration, escalation count, tool calls, RAG similarity.
PII filter: email, phone, SSN, credit card redaction with span events.

### Three-Layer OTel

1. **Java Agent** (zero-code): HTTP server spans, JDBC/R2DBC database spans, Spring framework spans
2. **Spring AI built-in** (Micrometer): ChatModel and VectorStore observation spans
3. **Manual spans** (OTel API): Pipeline stages, gateway contract compliance, domain metrics

### Verify Telemetry

```bash
./scripts/verify-scout.sh
```

## Development

```bash
make check    # build + test
make build    # compile
make test     # run tests
```

## LLM Providers

| Provider | Models | Usage |
| --- | --- | --- |
| OpenAI | gpt-4.1 (capable), gpt-4.1-mini (fast) | Default primary |
| Anthropic | claude-haiku-4-5-20251001 | Fallback (auto model switch via `FALLBACK_MODEL`) |
| Ollama | Any local model | `LLM_PROVIDER=ollama` |

## Failure Injection

Activate with Spring profile `failure-injection`. 8 scenarios for testing observability under failure:

1. **hallucinated-order** — nonexistent order lookup
2. **escalation-thrash** — angry customer triggering escalation
3. **tool-loop** — ambiguous input causing repeated tool calls
4. **rag-miss** — question outside KB coverage
5. **rate-limit** — high-volume request
6. **streaming-interrupt** — long response for SSE interruption
7. **sensitive-data** — PII in input, verify redaction
8. **context-overflow** — large conversation history

## Sample Conversations

- "What is the status of order ORD-10001?"
- "I want to return my headphones, order ORD-10005"
- "What products do you have in the audio category?"
- "I'm really frustrated, nothing is working. Let me talk to a human."
- "What is your return policy?"
