// Headless-browser driver for the telemetry demo. Connects to a Chrome DevTools
// endpoint (launched by verify-scout.sh), clicks through the flows that emit
// browser spans, Web Vitals metrics, and error logs, then force-flushes via
// pagehide. Requires Node 22+ (global WebSocket).
const CDP = process.env.CDP_URL || 'http://localhost:9222';
const APP = process.env.FRONTEND_URL || 'http://localhost:8080';

async function pickTarget() {
  const list = await (await fetch(`${CDP}/json`)).json();
  const page = list.find((t) => t.type === 'page');
  if (!page) throw new Error('no page target');
  return page.webSocketDebuggerUrl;
}

let id = 0;
const pending = new Map();
let ws;

function send(method, params = {}) {
  const msgId = ++id;
  ws.send(JSON.stringify({ id: msgId, method, params }));
  return new Promise((resolve, reject) => pending.set(msgId, { resolve, reject }));
}

async function evaluate(expression) {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) return { error: r.exceptionDetails.exception?.description || 'eval error' };
  return { value: r.result.value };
}

// Wait for a one-off event (e.g. Page.loadEventFired) after a call that triggers it.
const waiters = new Map();
function waitEvent(method, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(`timeout waiting ${method}`)), timeoutMs);
    waiters.set(method, { resolve, clear: () => clearTimeout(t) });
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const clickButton = (prefix) => evaluate(`
  (() => {
    const b = [...document.querySelectorAll('button')].find(x => x.textContent.trim().startsWith(${JSON.stringify(prefix)}));
    if (!b) return 'no-button';
    b.click();
    return 'clicked';
  })()
`);

async function main() {
  ws = new WebSocket(await pickTarget());
  await new Promise((res, rej) => {
    ws.addEventListener('open', res, { once: true });
    ws.addEventListener('error', rej, { once: true });
  });
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
    } else if (msg.method && waiters.has(msg.method)) {
      const w = waiters.get(msg.method);
      waiters.delete(msg.method);
      w.clear();
      w.resolve(msg);
    }
  });

  await send('Page.enable');
  await send('Runtime.enable');

  console.log(`navigate -> ${APP}/items`);
  await send('Page.navigate', { url: `${APP}/items` });
  await waitEvent('Page.loadEventFired');
  await sleep(1500); // Angular hydrate + SDK install

  console.log('page title:', JSON.stringify((await evaluate('document.title')).value));

  console.log('Load items:', (await clickButton('Load items')).value);
  await sleep(1500);
  console.log('rendered <li> rows:', (await evaluate('document.querySelectorAll("li").length')).value);

  // Route change /items -> /about -> /items => router.navigation spans
  await evaluate(`(() => { const a=[...document.querySelectorAll('nav a')].find(x=>x.textContent.trim()==='About'); if(a)a.click(); return 'about'; })()`);
  await sleep(1200);
  await evaluate(`(() => { const a=[...document.querySelectorAll('nav a')].find(x=>x.textContent.trim()==='Items'); if(a)a.click(); return 'items'; })()`);
  await sleep(1200);

  console.log('Trigger API error:', (await clickButton('Trigger API error')).value); // -> correlated ERROR log
  await sleep(1500);
  console.log('Trigger error:', (await clickButton('Trigger error')).value); // -> best-effort ERROR log
  await sleep(1200);

  await evaluate(`window.dispatchEvent(new Event('pagehide')); 'flushed'`); // force SDK flush
  console.log('dispatched pagehide (force flush)');
  await sleep(2500);

  ws.close();
  console.log('done');
  process.exit(0);
}

main().catch((e) => {
  console.error('DRIVER ERROR:', e.message);
  process.exit(1);
});
