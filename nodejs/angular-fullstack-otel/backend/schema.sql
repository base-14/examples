-- Angular Full-Stack OpenTelemetry Example - items table + seed data
CREATE TABLE IF NOT EXISTS items (
  id    SERIAL PRIMARY KEY,
  name  TEXT NOT NULL,
  price NUMERIC(10,2) NOT NULL
);

INSERT INTO items (name, price) VALUES
  ('Widget', 9.99),
  ('Gadget', 19.99),
  ('Sprocket', 4.50)
ON CONFLICT DO NOTHING;
