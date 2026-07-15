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

  assert.match(workspace, /apiFetch\("\/api\/session"/);
  assert.match(workspace, /apiFetch\("\/api\/chat"/);
  assert.match(workspace, /apiFetch\(`\/api\/design\/\$\{design\.design_id\}\/revise`/);
  assert.doesNotMatch(workspace, /OPENROUTER_API_KEY|openrouter\.ai|Authorization|Bearer |apiKey\s*[:=]/);
  assert.match(workspace, /progressStates = \["planning", "designing", "grounding", "checking", "revising", "passed", "failed", "error"\]/);
  assert.match(workspace, /tabs = \["shopping", "vastu"\]/);
  assert.match(workspace, /<ZoneGrid items=\{zoneItems\} \/>/);
  assert.match(workspace, /Shopping & materials/);
  assert.match(workspace, /Design revisions/);
  assert.match(workspace, /Furniture saved with this version/);
  assert.match(workspace, /concept_history/);
  assert.match(workspace, /selectedRevisionId/);
  assert.doesNotMatch(workspace, /Product photo collage/);
  assert.match(workspace, /Project Chat/);
  assert.match(workspace, /projectChats/);
  assert.match(workspace, /apiFetch\(`\/api\/projects\/\$\{encodeURIComponent\(projectId\)\}`/);
  assert.match(workspace, /Delete .*complete chat and design history/);
  assert.match(workspace, /apiFetch\("\/api\/auth\/me"\)/);
  assert.match(workspace, /credentials: "include"/);
  assert.doesNotMatch(workspace, /localStorage|sessionStorage/);
  assert.match(workspace, /conceptLoading/);
  assert.match(workspace, /concept-loading-card/);
  assert.match(workspace, /ys-chat-generating/);
  assert.match(workspace, /BeforeAfterSlider/);
  assert.match(workspace, /source_images/);
  assert.match(workspace, /revision_text/);
  assert.match(workspace, /base_revision_id/);
  assert.match(workspace, /selectedRevisionId/);
  assert.match(workspace, /refresh_products: refreshProducts/);
  assert.match(workspace, /Refresh furniture & image/);
  assert.match(workspace, /styleCards/);
  assert.match(workspace, /\/style-images\/modern\.png/);
  assert.match(workspace, /colour_palette: palettePrompt/);
  assert.match(workspace, /Show at least four palette colours/);
  assert.match(workspace, /ys-style-swatches/);
  assert.match(workspace, /Complete material list/);
  assert.match(workspace, /Wall paint/);
  assert.match(workspace, /Showpieces/);
  assert.match(data, /href: "\/workspace", label: "My projects"/);
});

test("workspace renders backend design data rather than app data catalogue fixtures", () => {
  assert.doesNotMatch(workspace, /\bplanItems\b|\bproductById\b|import\s*\{[^}]*\bproducts\b/);
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
  assert.match(workspace, /selectAlternative/);
  assert.match(workspace, /\/select-item/);
  assert.match(workspace, /Approved alternatives/);
  assert.match(workspace, /Find similar product/);
  assert.match(workspace, /Material/);
  assert.match(workspace, /Colour/);
});

test("workspace exposes Vastu, shopping, budget, revision, and error states", () => {
  assert.match(workspace, /critic_verdict\.vastu_result\?\.score/);
  assert.match(workspace, /item_results\.flatMap/);
  assert.match(workspace, /rule_results/);
  assert.match(workspace, /What YourSpace checked/);
  assert.match(workspace, /Real products/);
  assert.match(workspace, /Vastu & checks/);
  assert.match(workspace, /Design with Vastu guidance/);
  assert.match(workspace, /Placement priorities/);
  assert.match(workspace, /design-intelligence-strip/);
  assert.match(workspace, /visibleTotal === backendTotal/);
  assert.match(workspace, /budgetStatus/);
  assert.match(workspace, /budgetInput/);
  assert.match(workspace, /type="number"/);
  assert.match(workspace, /type="range"/);
  assert.match(workspace, /updateBudgetFromSlider/);
  assert.match(workspace, /reviseDesign/);
  assert.match(workspace, /Revising\.\.\./);
  assert.match(workspace, /Retry pending image/);
  assert.match(workspace, /retryPendingRevision/);
  assert.match(workspace, /Regenerate selected version/);
  assert.match(workspace, /Design version navigation/);
  assert.match(workspace, />Previous</);
  assert.match(workspace, />Next</);
  assert.match(workspace, /comparisonImage/);
  assert.match(workspace, /revision_mode: revisionMode/);
  assert.match(workspace, /"variation"/);
  assert.match(workspace, /role="alert"/);
  assert.match(workspace, /invalid_brief|no_catalogue_results|retry_exhausted|graph_failure|general error|missing_api_key|image_service_unavailable/);
});

test("T19 export brief uses backend export data and local share route", () => {
  assert.match(workspace, /Export selected version/);
  assert.match(workspace, /\?revision=\$\{encodeURIComponent\(selectedRevision\.revision_id\)\}/);
  assert.match(designBriefRoute, /revisionId=\{revisionId\}/);
  assert.match(designBriefRoute, /searchParams/);
  assert.match(exportBrief, /apiUrl\(`\/api\/export\/\$\{designId\}\$\{revisionQuery\}`\)/);
  assert.match(exportBrief, /revision_id=\$\{encodeURIComponent\(revisionId\)\}/);
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
    "Print or save PDF",
    "Download brief",
    "product-placeholder.svg",
  ]) {
    assert.match(exportBrief, new RegExp(required.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), required);
  }
  assert.match(exportBrief, /Design ID \{payload\.design_id\}/);
  assert.match(exportBrief, /Generated \{generatedAt\}/);
  assert.match(exportBrief, /User requirements/);
  assert.match(exportBrief, /Budget summary/);
  assert.match(exportBrief, /itemTotal === payload\.total_price_inr/);
  assert.match(exportBrief, /credentials: "include"/);
  assert.match(exportBrief, /cache: "no-store"/);
  assert.match(exportBrief, /window\.print\(\)/);
  assert.match(exportBrief, /waitForImages/);
  assert.match(exportBrief, /concept_image_data_url/);
  assert.match(exportBrief, /source_image_data_url/);
  assert.match(exportBrief, /imageSourceAsDataUrl/);
  assert.match(exportBrief, /new Blob\(\[html\]/);
  assert.match(css, /@page/);
  assert.match(css, /page-break-inside: avoid/);
  assert.match(css, /overflow: visible !important/);
});

test("T19 backend export reads stored design without regenerating", () => {
  const exportFn = apiMain.match(/def export_design\([\s\S]*?\) -> ExportResponse:[\s\S]*?return ExportResponse\(/);
  assert.ok(exportFn);
  assert.match(exportFn[0], /design = design_store\.get\(design_id\)/);
  assert.doesNotMatch(exportFn[0], /run_design_for_session|run_agent_loop/);
  assert.match(apiMain, /"generated_at": datetime\.now\(UTC\)\.isoformat\(\)/);
  assert.match(apiMain, /total_price = sum\(int\(item\["price_inr"\]\) for item in selected\)/);
  assert.match(apiMain, /stored design total does not match selected item prices/);
});

test("account and project access use backend sessions instead of editable browser identity", () => {
  const login = readFileSync("app/components/LoginClient.tsx", "utf8");
  assert.match(login, /\/api\/auth\/signup/);
  assert.match(login, /\/api\/auth\/login/);
  assert.match(login, /credentials: "include"/);
  assert.doesNotMatch(login + workspace, /formaos_homeowner|localStorage|sessionStorage/);
  assert.match(apiMain, /httponly=True/);
  assert.match(apiMain, /pbkdf2_hmac/);
  assert.match(apiMain, /authenticated_user/);
  assert.match(workspace, /disabled=\{index > step\}/);
  assert.match(workspace, /disabled=\{!design\}/);
  assert.match(login, /showPassword/);
  assert.match(login, /type=\{showPassword \? "text" : "password"\}/);
  assert.match(login, /Hide password/);
  assert.match(apiMain, /@app\.delete\("\/api\/projects\/\{project_id\}"/);
  assert.match(apiMain, /delete_project\(project_id, user\["id"\]\)/);
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
