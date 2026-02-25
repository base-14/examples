CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Knowledge base articles (for RAG retrieval)
CREATE TABLE kb_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intent VARCHAR(100) NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    category VARCHAR(100),
    tags TEXT[],
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_kb_intent ON kb_articles(intent);
CREATE INDEX idx_kb_embedding ON kb_articles USING hnsw (embedding vector_cosine_ops);

-- Products
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(300) NOT NULL,
    description TEXT,
    category VARCHAR(100) NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    sku VARCHAR(50) UNIQUE NOT NULL,
    in_stock BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_sku ON products(sku);

-- Customers
CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    email VARCHAR(300) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Orders
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id VARCHAR(20) UNIQUE NOT NULL,
    customer_id UUID NOT NULL REFERENCES customers(id),
    status VARCHAR(30) NOT NULL,
    tracking_number VARCHAR(100),
    estimated_delivery DATE,
    total_amount NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_orders_order_id ON orders(order_id);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_status ON orders(status);

-- Order items
CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);

CREATE INDEX idx_order_items_order ON order_items(order_id);

-- Returns
CREATE TABLE returns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    return_id VARCHAR(20) UNIQUE NOT NULL,
    order_id UUID NOT NULL REFERENCES orders(id),
    reason TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    refund_amount NUMERIC(10, 2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_returns_return_id ON returns(return_id);
CREATE INDEX idx_returns_order ON returns(order_id);

-- Conversations
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers(id),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    escalated BOOLEAN DEFAULT false,
    escalation_reason VARCHAR(200),
    total_turns INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost_usd NUMERIC(10, 6) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_conversations_status ON conversations(status);
CREATE INDEX idx_conversations_customer ON conversations(customer_id);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    intent VARCHAR(50),
    confidence NUMERIC(3, 2),
    tools_called TEXT[],
    tokens_used INTEGER,
    cost_usd NUMERIC(10, 6),
    trace_id VARCHAR(32),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);

-- Spring AI vector store table (created by Spring AI, but we define it here for seed data)
CREATE TABLE IF NOT EXISTS vector_store (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    metadata JSONB,
    embedding VECTOR(1536)
);

CREATE INDEX IF NOT EXISTS idx_vector_store_embedding ON vector_store USING hnsw (embedding vector_cosine_ops);
