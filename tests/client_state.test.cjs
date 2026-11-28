const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { runInNewContext } = require("node:vm");

const appPath = path.resolve(__dirname, "../src/dashboard/static/app.js");
const source = readFileSync(appPath, "utf8");

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function boot(handleRequest) {
  const storage = new Map();
  const elements = new Map();
  const listeners = new Map();
  const firstRender = deferred();
  const element = (id) => {
    if (!elements.has(id)) {
      elements.set(id, {
        open: false,
        classList: { add() {}, remove() {} },
        close() { this.open = false; },
        showModal() { this.open = true; },
      });
    }
    return elements.get(id);
  };
  const context = {
    crypto: { randomUUID },
    document: {
      getElementById: element,
      addEventListener: (name, listener) => listeners.set(name, listener),
    },
    window: { addEventListener() {} },
    location: { hash: "#history" },
    sessionStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
    fetch: async (url, options) => ({
      ok: true,
      json: async () => handleRequest(new URL(url, "http://localhost"), options),
    }),
    clearTimeout() {},
    setTimeout() {},
    notifyRender: firstRender.resolve,
  };
  // Only rendering is stubbed. Events, refresh ordering, and request-key handling
  // use the same front-end script served by FastAPI. No live service is contacted.
  runInNewContext(
    source + "\nrender = () => notifyRender();",
    context,
    { filename: appPath },
  );
  return {
    ready: firstRender.promise,
    element,
    storage,
    click: (action, id) => listeners.get("click")({
      target: {
        closest: (selector) => selector === "[data-action]"
          ? { dataset: { action, id } }
          : null,
      },
    }),
  };
}

function workspaceOrEvidence(url) {
  if (url.pathname === "/api/edition") {
    return { workspace: "BUSINESS_LOCAL", gates: { business: { id: "G-1", status: "BLOCKED" } } };
  }
  if (url.pathname === "/api/workspace") {
    return { selected: { id: url.searchParams.get("run_id") || "previous-run", state: "paused" } };
  }
  assert.match(url.pathname, /^\/api\/runs\/[^/]+\/evidence$/);
  return { attempts: [] };
}

test("resuming another batch preserves the key of an interrupted new request", { timeout: 5000 }, async () => {
  const created = [];
  const resumed = [];
  const app = boot((url, options) => {
    if (options.method !== "POST") return workspaceOrEvidence(url);
    if (url.pathname === "/api/runs/previous-run/resume") {
      resumed.push(options.body);
      return { run_id: "previous-run" };
    }
    assert.equal(url.pathname, "/api/runs");
    created.push(JSON.parse(options.body).request_key);
    if (created.length === 1) throw new Error("First result could not be read");
    return { run_id: "new-run" };
  });
  await app.ready;
  await app.click("commit-run");
  const key = app.storage.get("voc-pending-request");
  assert.ok(key);
  await app.click("commit-resume");
  assert.deepEqual(resumed, [undefined]);
  assert.equal(app.storage.get("voc-pending-request"), key);
  await app.click("commit-run");
  assert.deepEqual(created, [key, key]);
  assert.equal(app.storage.has("voc-pending-request"), false);
});

test("a slow earlier evidence read cannot replace the last selected batch", { timeout: 5000 }, async () => {
  const slowStarted = deferred();
  const slowResult = deferred();
  const app = boot((url) => {
    if (url.pathname === "/api/runs/slow-run/evidence") {
      slowStarted.resolve();
      return slowResult.promise;
    }
    return workspaceOrEvidence(url);
  });
  await app.ready;
  const first = app.click("open-run", "slow-run");
  await slowStarted.promise;
  await app.click("open-run", "latest-run");
  assert.match(app.element("drawer-title").textContent, /latest-r/);
  slowResult.resolve({ attempts: [] });
  await first;
  assert.match(app.element("drawer-title").textContent, /latest-r/);
  assert.match(app.element("drawer-body").innerHTML, /latest-run/);
});
