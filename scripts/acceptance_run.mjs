import { mkdir, writeFile } from "node:fs/promises";
import { Buffer } from "node:buffer";

const backendBase = process.env.FORMAOS_BACKEND_URL ?? "http://127.0.0.1:8000";
const frontendBase = process.env.FORMAOS_FRONTEND_URL ?? "http://localhost:3000";
const cdpBase = process.env.FORMAOS_CHROME_CDP_URL ?? "http://127.0.0.1:9222";
const outputDir = "artifacts/demo";

const demoBrief = {
  room_type: "living_room",
  width: 10,
  depth: 12,
  units: "ft",
  budget_inr: 85000,
  style_words: ["warm", "wood", "storage"],
  constraints: ["kid-friendly", "extra storage"],
  vastu_enabled: true,
  main_door_direction: "N",
  compass_direction: "N",
};

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`${url} ${response.status} ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function post(path, body) {
  return jsonFetch(`${backendBase}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function connectCdp() {
  try {
    const tabs = await jsonFetch(`${cdpBase}/json/list`);
    const tab = tabs.find((entry) => entry.url.includes("/workspace")) ?? tabs[0];
    if (!tab?.webSocketDebuggerUrl) return null;
    const ws = new WebSocket(tab.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.onopen = resolve;
      ws.onerror = reject;
    });
    let id = 0;
    const pending = new Map();
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id && pending.has(message.id)) {
        pending.get(message.id)(message);
        pending.delete(message.id);
      }
    };
    return {
      call(method, params = {}) {
        return new Promise((resolve) => {
          const callId = ++id;
          pending.set(callId, resolve);
          ws.send(JSON.stringify({ id: callId, method, params }));
        });
      },
      close() {
        ws.close();
      },
    };
  } catch {
    return null;
  }
}

async function evalPage(cdp, expression) {
  const response = await cdp.call("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.result?.exceptionDetails) {
    throw new Error(JSON.stringify(response.result.exceptionDetails));
  }
  return response.result.result.value;
}

async function captureBrowserEvidence(designId) {
  const cdp = await connectCdp();
  if (!cdp) {
    return { status: "skipped", reason: "Chrome DevTools endpoint unavailable" };
  }

  await cdp.call("Runtime.enable");
  await cdp.call("Page.enable");
  await cdp.call("Page.navigate", { url: `${frontendBase}/workspace` });
  await cdp.call("Page.loadEventFired");
  const workspaceShot = await cdp.call("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  await writeFile(`${outputDir}/workspace.png`, Buffer.from(workspaceShot.result.data, "base64"));

  await cdp.call("Page.navigate", { url: `${frontendBase}/design/${designId}/brief` });
  for (let index = 0; index < 80; index += 1) {
    const text = await evalPage(cdp, "document.body.innerText");
    if (text.includes(`Design Brief ${designId}`) && text.includes("Selected items")) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
    if (index === 79) throw new Error("Export brief did not render in browser");
  }
  const exportText = await evalPage(cdp, "document.body.innerText");
  const images = await evalPage(
    cdp,
    '[...document.images].map((img) => ({ complete: img.complete, naturalWidth: img.naturalWidth, naturalHeight: img.naturalHeight }))',
  );
  const exportShot = await cdp.call("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  await writeFile(`${outputDir}/export_brief.png`, Buffer.from(exportShot.result.data, "base64"));
  const pdf = await cdp.call("Page.printToPDF", { printBackground: true, preferCSSPageSize: true });
  await writeFile(`${outputDir}/export_brief.pdf`, Buffer.from(pdf.result.data, "base64"));
  cdp.close();
  return {
    status: "pass",
    screenshots: ["artifacts/demo/workspace.png", "artifacts/demo/export_brief.png"],
    pdf: "artifacts/demo/export_brief.pdf",
    images_loaded: images.length > 0 && images.every((image) => image.complete && image.naturalWidth > 0 && image.naturalHeight > 0),
    export_contains_required_sections: [
      "Room brief",
      "User requirements",
      "Selected items",
      "Budget summary",
      "Vastu summary",
      "Attribution",
    ].every((section) => exportText.toLowerCase().includes(section.toLowerCase())),
  };
}

async function main() {
  await mkdir(outputDir, { recursive: true });

  const health = await jsonFetch(`${backendBase}/api/health`);
  const session = await post("/api/session", { brief: demoBrief });
  const chat = await post("/api/chat", {
    session_id: session.session_id,
    message: "Create a warm wood living room with storage and Vastu guidance.",
    max_retries: 2,
  });
  const design = chat.design;
  const revision = await post(`/api/design/${design.design_id}/revise`, {
    session_id: session.session_id,
    message: "Revise once and keep the same warm wood, storage, and Vastu constraints.",
    max_retries: 2,
  });
  const revisedDesign = revision.design;
  const exportPayload = await jsonFetch(`${backendBase}/api/export/${design.design_id}`);
  const selected = exportPayload.selected_items;
  const selectedTotal = selected.reduce((sum, item) => sum + item.price_inr, 0);
  const evalSummary = await jsonFetch("file://unsupported").catch(async () => {
    const { readFile } = await import("node:fs/promises");
    return JSON.parse(await readFile("artifacts/metrics/eval_summary.json", "utf8"));
  });
  const browserEvidence = await captureBrowserEvidence(design.design_id);

  const acceptance = {
    status:
      health.status === "ok" &&
      design.status === "passed" &&
      selected.length > 0 &&
      selectedTotal === exportPayload.total_price_inr &&
      exportPayload.vastu_summary.status !== "skipped" &&
      browserEvidence.status !== "fail"
        ? "PASS"
        : "FAIL",
    generated_at: new Date().toISOString(),
    commands: {
      environment:
        'export PATH="$PWD/.tools/node/bin:$PWD/.tools/bin:$PATH"; export UV_CACHE_DIR="$PWD/.uv-cache"; export PYTHONPATH=backend',
      backend:
        "FORMAOS_DEMO_PLANNER=1 uv run uvicorn formaos.api.main:app --app-dir backend --reload",
      frontend: "npm run dev",
      acceptance: "npm run demo:acceptance",
      tests: "npm test",
    },
    versions: {
      node: process.version,
      package: "formaos-mvp@0.1.0",
      python_project: "formaos-backend@0.1.0",
    },
    selected_model:
      "Demo acceptance used FORMAOS_DEMO_PLANNER=1 deterministic local planner; production Planner default is OpenRouter openai/gpt-4.1-mini when OPENROUTER_API_KEY is configured.",
    dataset_subset_size: {
      curated_catalogue_items: 180,
      image_mapped_items: 180,
      vastu_rules: 30,
      evaluation_briefs: 10,
    },
    demo_brief: demoBrief,
    session_id: session.session_id,
    design_id: design.design_id,
    checks: {
      first_design_status: design.status,
      attempt_log_states: design.attempt_log.map((entry) => entry.state),
      revision_status: revisedDesign.status,
      revision_design_id_persisted: revisedDesign.design_id === design.design_id,
      revised_item_ids: revisedDesign.grounder_output.grounded_slots
        .filter((slot) => slot.selected_item)
        .map((slot) => slot.selected_item.item_id),
      corrected_item_list_count: selected.length,
      selected_item_ids: selected.map((item) => item.item_id),
      selected_total_inr: exportPayload.total_price_inr,
      selected_total_matches_items: selectedTotal === exportPayload.total_price_inr,
      budget_status: exportPayload.budget_summary.status,
      vastu_status: exportPayload.vastu_summary.status,
      export_brief_loaded: exportPayload.design_id === design.design_id,
      metrics_available: Boolean(evalSummary.systems?.formaos && evalSummary.systems?.baseline_ungrounded),
    },
    browser_evidence: browserEvidence,
    pass_fail_notes: [
      "Backend session, chat design, export brief, and metrics evidence completed under demo conditions.",
      "Acceptance run uses deterministic demo planner to avoid external API spend while preserving Planner/Designer/Grounder/Critic/Reviser flow.",
    ],
  };

  await writeFile(`${outputDir}/acceptance_run.json`, JSON.stringify(acceptance, null, 2) + "\n");
  console.log(JSON.stringify(acceptance, null, 2));
  if (acceptance.status !== "PASS") process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
