import { context, propagation } from "@opentelemetry/api";
import { logger } from "./logger";

const notifyUrl = process.env.NOTIFY_URL ?? "http://localhost:8081";

export async function notifyArticleCreated(articleId: number, title: string) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  propagation.inject(context.active(), headers);

  try {
    const res = await fetch(`${notifyUrl}/notify`, {
      method: "POST",
      headers,
      body: JSON.stringify({ event: "article.created", article_id: articleId, title }),
    });
    if (!res.ok) {
      logger.warn("Notify service returned non-OK", { status: res.status });
    }
  } catch (err) {
    logger.warn("Notify service unreachable", { error: String(err) });
  }
}
