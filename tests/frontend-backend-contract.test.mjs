import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const planner = readFileSync("app/components/PlannerTool.tsx", "utf8");
const contracts = readFileSync("backend/formaos/contracts.py", "utf8");
const zoneGrid = readFileSync("app/components/ZoneGrid.tsx", "utf8");
const vastuPage = readFileSync("app/vastu/page.tsx", "utf8");
const data = readFileSync("app/data.ts", "utf8");
const workspace = readFileSync("app/components/WorkspaceClient.tsx", "utf8");
const exportBrief = readFileSync("app/components/ExportBriefClient.tsx", "utf8");
const designBriefRoute = readFileSync("app/design/[id]/brief/page.tsx", "utf8");
const apiMain = readFileSync("backend/formaos/api/main.py", "utf8");
const css = readFileSync("app/globals.css", "utf8");

test("planner sends backend RoomBrief contract fields to /api/session", () => {
  const fields = [
    "room_type",
    "width",
    "depth",
    "units",
    "budget_inr",
    "style_words",
    "constraints",
    "vastu_enabled",
    "main_door_direction",
    "compass_direction",
  ];
  for (const field of fields) {
    assert.match(planner, new RegExp(`\\b${field}\\b\\s*[:,]`), field);
  }
  assert.match(planner, /fetch\("\/api\/session"/);
  assert.match(planner, /body: JSON\.stringify\(\{ brief: roomBrief \}\)/);
});

test("workspace owns the core T18 journey and calls only backend API routes", () => {
  for (const field of [
    "room_type",
    "width",
    "depth",
    "units",
    "budget_inr",
    "style_words",
    "constraints",
    "vastu_enabled",
    "main_door_direction",
    "compass_direction",
  ]) {
    assert.match(workspace, new RegExp(`\\b${field}\\b\\s*[:,]`), field);
  }

  assert.match(workspace, /apiUrl\("\/api\/session"\)/);
  assert.match(workspace, /apiUrl\("\/api\/chat"\)/);
  assert.match(workspace, /apiUrl\(`\/api\/design\/\$\{design\.design_id\}\/revise`\)/);
  assert.doesNotMatch(workspace, /OPENROUTER_API_KEY|openrouter\.ai|Authorization|Bearer |apiKey\s*[:=]/);
  assert.match(workspace, /progressStates = \["planning", "designing", "grounding", "checking", "revising", "passed", "failed", "error"\]/);
  assert.match(workspace, /tabs = \["items", "vastu", "shopping"\]/);
  assert.match(workspace, /<ZoneGrid items=\{zoneItems\} \/>/);
  assert.match(workspace, /Grounded item cards/);
  assert.match(workspace, /Product photo collage/);
  assert.match(data, /href: "\/workspace", label: "Workspace"/);
});

test("workspace renders backend design data rather than app data catalogue fixtures", () => {
  assert.doesNotMatch(workspace, /planItems|productById|products/);
  assert.match(workspace, /selected_item/);
  assert.match(workspace, /item\.item_id/);
  assert.match(workspace, /item\.title/);
  assert.match(workspace, /item\.price_inr/);
  assert.match(workspace, /item\.width_cm/);
  assert.match(workspace, /item\.depth_cm/);
  assert.match(workspace, /item\.height_cm/);
  assert.match(workspace, /safeImagePath\(item\)/);
  assert.match(workspace, /product-placeholder\.svg/);
  assert.match(workspace, /slot\.alternatives\.slice\(0, 3\)/);
});

test("workspace exposes Vastu, shopping, budget, revision, and error states", () => {
  assert.match(workspace, /critic_verdict\.vastu_result\?\.score/);
  assert.match(workspace, /item_results\.flatMap/);
  assert.match(workspace, /rule_results/);
  assert.match(workspace, /Palette suggestions/);
  assert.match(workspace, /Actionable notes/);
  assert.match(workspace, /visibleTotal === backendTotal/);
  assert.match(workspace, /budgetStatus/);
  assert.match(workspace, /reviseDesign/);
  assert.match(workspace, /role="alert"/);
  assert.match(workspace, /invalid_brief|no_catalogue_results|retry_exhausted|graph_failure|general error|missing_api_key/);
});

test("T19 export brief uses backend export data and local share route", () => {
  assert.match(workspace, /href=\{`\/design\/\$\{design\.design_id\}\/brief`\}/);
  assert.match(designBriefRoute, /ExportBriefClient designId=\{id\}/);
  assert.match(exportBrief, /apiUrl\(`\/api\/export\/\$\{designId\}`\)/);
  assert.doesNotMatch(exportBrief, /planItems|productById|demoBrief|attempts/);
  for (const required of [
    "room_brief",
    "generated_at",
    "user_requirements",
    "selected_items",
    "total_price_inr",
    "budget_summary",
    "fit_notes",
    "vastu_summary",
    "attribution",
    "Amazon Berkeley Objects",
    "curated indicative demo values",
    "Print PDF",
    "product-placeholder.svg",
  ]) {
    assert.match(exportBrief, new RegExp(required.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), required);
  }
  assert.match(exportBrief, /Design ID \{payload\.design_id\}/);
  assert.match(exportBrief, /Generated \{generatedAt\}/);
  assert.match(exportBrief, /User requirements/);
  assert.match(exportBrief, /Budget summary/);
  assert.match(exportBrief, /itemTotal === payload\.total_price_inr/);
  assert.match(css, /@page/);
  assert.match(css, /page-break-inside: avoid/);
  assert.match(css, /overflow: visible !important/);
});

test("T19 backend export reads stored design without regenerating", () => {
  const exportFn = apiMain.match(/def export_design\(design_id: str\) -> ExportResponse:[\s\S]*?return ExportResponse\(/);
  assert.ok(exportFn);
  assert.match(exportFn[0], /design = design_store\.get\(design_id\)/);
  assert.doesNotMatch(exportFn[0], /run_design_for_session|run_agent_loop/);
  assert.match(apiMain, /"generated_at": datetime\.now\(UTC\)\.isoformat\(\)/);
  assert.match(apiMain, /total_price = sum\(int\(item\["price_inr"\]\) for item in selected\)/);
  assert.match(apiMain, /stored design total does not match selected item prices/);
});

test("planner direction values match backend Direction values", () => {
  const backendMatch = contracts.match(/Direction = Literal\[(.*?)\]/s);
  assert.ok(backendMatch);
  const backendDirections = [...backendMatch[1].matchAll(/"([^"]+)"/g)].map((match) => match[1]);
  const frontendMatch = planner.match(/const directionOptions = \[(.*?)\]/s);
  assert.ok(frontendMatch);
  const frontendDirections = [...frontendMatch[1].matchAll(/"([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(frontendDirections, backendDirections);
});

test("vastu zone grid uses required 3 by 3 zone order and placement chips", () => {
  const backendMatch = contracts.match(/Direction = Literal\[(.*?)\]/s);
  assert.ok(backendMatch);
  const backendDirections = [...backendMatch[1].matchAll(/"([^"]+)"/g)].map((match) => match[1]);
  const frontendMatch = zoneGrid.match(/zones = \[(.*?)\] as const/s);
  assert.ok(frontendMatch);
  const frontendZones = [...frontendMatch[1].matchAll(/"([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(frontendZones, ["NW", "N", "NE", "W", "C", "E", "SW", "S", "SE"]);
  assert.deepEqual([...frontendZones].sort(), [...backendDirections].sort());
  assert.match(zoneGrid, /zone-chip/);
  assert.match(zoneGrid, /items\.filter\(\(item\) => item\.zone === zone\)/);
  assert.match(vastuPage, /<ZoneGrid items=\{planItems\} \/>/);
  assert.match(data, /zone:\s*"S"/);
  assert.match(data, /zone:\s*"C"/);
  assert.match(data, /zone:\s*"W"/);
  assert.match(data, /zone:\s*"SE"/);
});
