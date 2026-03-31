import { pgTable, serial, text, timestamp, varchar } from "drizzle-orm/pg-core";

export const articles = pgTable("articles", {
  id: serial().primaryKey(),
  title: varchar({ length: 255 }).notNull(),
  body: text().notNull(),
  createdAt: timestamp("created_at", { precision: 3 }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { precision: 3 }).notNull().defaultNow(),
});
