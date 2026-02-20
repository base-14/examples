import { Hono } from "hono";
import { getPool } from "../db/pool.ts";

const health = new Hono();

health.get("/health", async (c) => {
  const pool = getPool();
  try {
    await pool.query("SELECT 1");
    return c.json({ status: "ok", db: "connected" });
  } catch {
    return c.json({ status: "error", db: "disconnected" }, 503);
  }
});

export { health };
