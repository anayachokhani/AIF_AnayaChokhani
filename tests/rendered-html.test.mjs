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
  assert.match(html, /<title>YourSpace<\/title>/i);
  assert.match(html, /AI-designed homes/);
  assert.match(html, /grounded/);
  assert.match(html, /Start designing/);
  assert.match(html, /Design your space in/);
  for (const id of ["how", "styles", "features", "pricing", "about"]) {
    assert.match(html, new RegExp(`href="#${id}"`));
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(html, /Distinct looks, not generic rooms/);
  assert.match(html, /Interior design that respects the actual home/);
  assert.doesNotMatch(html, /Your site is taking shape|react-loading-skeleton|codex-preview/i);
});

test("keeps the starter preview removed from product files", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(layout, /title:\s*"YourSpace"/);
  assert.match(page, /AI-designed homes/);
  assert.match(page, /Design your space in/);
  assert.doesNotMatch(page + layout + packageJson, /SkeletonPreview|codex-preview|react-loading-skeleton/);
});

test("server-renders the homeowner login shell", async () => {
  const response = await render("/login?next=/workspace");
  assert.equal(response.status, 200);

  const html = await response.text();
  assert.match(html, /Your private design studio/);
  assert.match(html, /Every room, revision, and recommendation/);
  assert.match(html, /Sign in/);
  assert.match(html, /Create account/);
});

test("server-renders the T18 workspace shell", async () => {
  const response = await render("/workspace");
  assert.equal(response.status, 200);

  const html = await response.text();
  assert.match(html, /Opening your private design studio/);
  const workspace = await readFile(new URL("../app/components/WorkspaceClient.tsx", import.meta.url), "utf8");
  assert.match(workspace, /FormaOS design workspace/);
  assert.match(workspace, /get to know your space/);
  assert.match(workspace, /Shopping & materials/);
  assert.match(workspace, /Design workspace tabs/);
  assert.match(workspace, /Shopping list/);
  assert.match(workspace, /Vastu & checks/);
});

test("workspace does not use remote placeholder room thumbnails", async () => {
  const workspace = await readFile(new URL("../app/components/WorkspaceClient.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(workspace, /images\.unsplash\.com|googleusercontent|google\.com/i);
  assert.match(workspace, /preview_image_data_url/);
  assert.match(workspace, /project_id/);
  assert.match(workspace, /photo_data_urls/);
  assert.match(workspace, /readAsDataURL/);
  assert.match(workspace, /style-images\/industrial\.png/);
  assert.match(workspace, /finishScheduleFor/);
  assert.doesNotMatch(workspace, /sampleRooms/);
});

test("server-renders the T19 local export brief route shell", async () => {
  const response = await render("/design/demo-design/brief");
  assert.equal(response.status, 200);

  const html = await response.text();
  assert.match(html, /Export brief/);
  assert.match(html, /Loading design brief/);
  assert.match(html, /Fetching the saved design, catalogue items, prices, and checks/);
});
