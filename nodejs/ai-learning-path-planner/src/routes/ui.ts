import { Hono } from "hono";

// A single self-contained page: no framework, no external assets, and an empty inline
// favicon so the browser does not request /favicon.ico and leave a 404 span in the trace.
const page = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Learning Path Planner</title>
<link rel="icon" href="data:,">
<style>
  body { font: 16px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 48rem; padding: 0 1rem; color: #1a1a1a; }
  h1 { font-size: 1.5rem; }
  form { display: flex; gap: .5rem; margin-bottom: 1rem; }
  input[type=text] { flex: 1; font: inherit; padding: .5rem; }
  button { font: inherit; padding: .5rem 1rem; }
  #status { color: #555; min-height: 1.5rem; }
  .week { margin: 1.5rem 0; }
  .week h2 { font-size: 1.1rem; margin: 0 0 .5rem; }
  .step { margin: 0 0 .75rem; padding-left: 1rem; border-left: 3px solid #ddd; }
  .step .path { font-family: ui-monospace, monospace; font-size: .9rem; }
  .kind { font-size: .75rem; padding: 0 .4rem; border-radius: .25rem; background: #eee; margin-left: .5rem; }
  .gaps { color: #7a4a00; }
  .error { color: #a00; }
</style>
</head>
<body>
<h1>AI Learning Path Planner</h1>
<form id="form">
  <input type="text" name="topic" placeholder="OpenTelemetry tracing for Node.js services" required autofocus>
  <button type="submit">Plan</button>
</form>
<p id="status"></p>
<div id="result"></div>
<script>
const form = document.getElementById("form");
const status = document.getElementById("status");
const result = document.getElementById("result");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderPlan(plan) {
  result.replaceChildren();
  for (const week of plan.weeks) {
    const section = el("section", "week");
    section.append(el("h2", null, week.subtopic));
    for (const step of week.steps) {
      const box = el("div", "step");
      const title = el("strong", null, step.title);
      title.append(el("span", "kind", step.kind));
      box.append(title, el("div", "path", step.path), el("div", null, step.why));
      section.append(box);
    }
    result.append(section);
  }
  if (plan.gaps.length > 0) {
    const gaps = el("section", "gaps");
    gaps.append(el("h2", null, "Gaps"));
    for (const gap of plan.gaps) gaps.append(el("p", null, gap.term + ": " + gap.reason));
    result.append(gaps);
  }
}

function handleLine(line) {
  const event = JSON.parse(line);
  if (event.event === "accepted") {
    status.replaceChildren("Accepted as run ", el("code", null, event.id), ". Researching, this takes a couple of minutes.");
  } else if (event.event === "plan") {
    const link = el("a", null, "JSON");
    link.href = "/plans/" + event.id;
    status.replaceChildren("Run " + event.id + " " + event.status + ". ", link);
    renderPlan(event.plan);
  } else if (event.event === "error") {
    status.replaceChildren(el("span", "error", "Run " + event.id + " failed: " + event.message));
  }
}

form.addEventListener("submit", async (submit) => {
  submit.preventDefault();
  const topic = new FormData(form).get("topic");
  result.replaceChildren();
  status.textContent = "Sending...";
  const res = await fetch("/plans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic }),
  });
  if (res.status === 422) {
    status.replaceChildren(el("span", "error", "The corpus has no coverage of that topic. Nothing was researched."));
    return;
  }
  if (!res.ok) {
    status.replaceChildren(el("span", "error", "Request failed with status " + res.status + "."));
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffered += decoder.decode(value, { stream: true });
    let newline = buffered.indexOf("\\n");
    while (newline >= 0) {
      const line = buffered.slice(0, newline).trim();
      buffered = buffered.slice(newline + 1);
      if (line) handleLine(line);
      newline = buffered.indexOf("\\n");
    }
  }
  if (buffered.trim()) handleLine(buffered.trim());
});
</script>
</body>
</html>
`;

export function uiRoutes(): Hono {
  const ui = new Hono();

  ui.get("/", (c) => c.html(page));

  return ui;
}
