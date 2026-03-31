import { Elysia } from "elysia";
import { db } from "../db";
import { sql } from "drizzle-orm";

export const healthRoutes = new Elysia().get("/api/health", async ({ set }) => {
  try {
    await db.execute(sql`SELECT 1`);
    return { status: "healthy", service: "elysia-articles" };
  } catch {
    set.status = 503;
    return { status: "unhealthy", service: "elysia-articles" };
  }
});
