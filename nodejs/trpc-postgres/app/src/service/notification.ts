import logger from "../lib/logger";

const NOTIFY_URL = process.env.NOTIFY_URL || "http://localhost:8081";

export async function notifyArticleCreated(article: {
  id: number;
  title: string;
}) {
  try {
    const res = await fetch(`${NOTIFY_URL}/notify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event: "article.created",
        article_id: article.id,
        title: article.title,
      }),
    });
    if (!res.ok) {
      logger.warn(
        { status: res.status, article_id: article.id },
        "Notify service returned non-OK"
      );
    }
  } catch (err) {
    logger.error({ err, article_id: article.id }, "Notify service unreachable");
  }
}
