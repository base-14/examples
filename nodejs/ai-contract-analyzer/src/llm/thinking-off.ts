type FetchLike = (input: string | URL | Request, init?: RequestInit) => Promise<Response>;

/**
 * Ollama returns a thinking model's chain of thought on its own channel and
 * leaves the message content empty, so structured output has nothing to parse.
 * Ollama turns thinking off with `reasoning_effort: "none"` on the chat
 * completions route and `reasoning: { effort: "none" }` on the responses route,
 * but the AI SDK drops both for any model it does not class as a reasoning
 * model, so the field goes on the request here instead. The responses route
 * ignores the chat completions field name and thinks until the request times out.
 *
 * Only chat requests are rewritten; the embeddings endpoint has no such field.
 * Every request also turns off Bun's 300 s fetch timeout, which an abort signal
 * cannot extend, because a local model can take longer than that on the extract
 * stage.
 */
export const thinkingOff: FetchLike = (input, init) => {
  const route = chatRoute(input);
  if (typeof init?.body !== "string" || route === null) return fetch(input, noFetchTimeout(init));

  let body: Record<string, unknown>;
  try {
    body = JSON.parse(init.body);
  } catch {
    return fetch(input, noFetchTimeout(init));
  }

  if (route === "responses") {
    body.reasoning = { effort: "none" };
  } else {
    body.reasoning_effort = "none";
  }
  return fetch(input, noFetchTimeout({ ...init, body: JSON.stringify(body) }));
};

function noFetchTimeout(init: RequestInit | undefined): RequestInit {
  return { ...init, timeout: false } as RequestInit;
}

function chatRoute(input: string | URL | Request): "responses" | "chat" | null {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  if (url.endsWith("/responses")) return "responses";
  if (url.endsWith("/chat/completions")) return "chat";
  return null;
}
