import { describe, expect, it } from "vitest";
import { uiRoutes } from "../../src/routes/ui.ts";

describe("GET /", () => {
  it("serves the planner page as HTML", async () => {
    const res = await uiRoutes().request("/");

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/html");
  });

  it("carries a topic form that posts to /plans", async () => {
    const html = await (await uiRoutes().request("/")).text();

    expect(html).toContain('name="topic"');
    expect(html).toContain('fetch("/plans"');
  });

  it("declares an inline favicon so the browser never requests /favicon.ico", async () => {
    const html = await (await uiRoutes().request("/")).text();

    expect(html).toContain('<link rel="icon" href="data:,">');
  });
});
