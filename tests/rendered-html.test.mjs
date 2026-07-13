import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${path}`, {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the FormaOS overview", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>FormaOS MVP<\/title>/i);
  assert.match(html, /FormaOS turns a room idea into a buildable plan/);
  assert.match(html, /Overview/);
  assert.match(html, /Planner/);
  assert.match(html, /Catalogue/);
  assert.doesNotMatch(html, /Your site is taking shape|react-loading-skeleton|codex-preview/i);
});

test("keeps the starter preview removed from product files", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(layout, /title:\s*"FormaOS MVP"/);
  assert.match(page, /Grounded home design MVP/);
  assert.doesNotMatch(page + layout + packageJson, /SkeletonPreview|codex-preview|react-loading-skeleton/);
});

test("server-renders the T18 workspace shell", async () => {
  const response = await render("/workspace");
  assert.equal(response.status, 200);

  const html = await response.text();
  assert.match(html, /FormaOS design workspace/);
  assert.match(html, /Room setup and chat/);
  assert.match(html, /planning/);
  assert.match(html, /designing/);
  assert.match(html, /grounding/);
  assert.match(html, /checking/);
  assert.match(html, /revising/);
  assert.match(html, /passed/);
  assert.match(html, /failed/);
  assert.match(html, /error/);
  assert.match(html, /Empty design state/);
  assert.match(html, /Grounded item cards/);
  assert.match(html, /Design workspace tabs/);
  assert.match(html, /Shopping list/);
});

test("server-renders the T19 local export brief route shell", async () => {
  const response = await render("/design/demo-design/brief");
  assert.equal(response.status, 200);

  const html = await response.text();
  assert.match(html, /Export brief/);
  assert.match(html, /Loading design brief/);
  assert.match(html, /Fetching the saved design, catalogue items, prices, and checks/);
});
