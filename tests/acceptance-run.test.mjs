import assert from "node:assert/strict";
import { existsSync, readFileSync, statSync } from "node:fs";
import test from "node:test";

const acceptance = JSON.parse(readFileSync("artifacts/demo/acceptance_run.json", "utf8"));
const demoScript = readFileSync("docs/demo_script.md", "utf8");

test("T22 acceptance run records required pass evidence", () => {
  assert.equal(acceptance.status, "PASS");
  for (const field of ["commands", "versions", "selected_model", "dataset_subset_size", "demo_brief", "design_id", "checks", "browser_evidence"]) {
    assert.ok(field in acceptance, field);
  }
  assert.match(acceptance.commands.backend, /FORMAOS_DEMO_PLANNER=1/);
  assert.match(acceptance.commands.frontend, /npm run dev/);
  assert.match(acceptance.commands.acceptance, /npm run demo:acceptance/);
  assert.equal(acceptance.dataset_subset_size.curated_catalogue_items, 180);
  assert.equal(acceptance.dataset_subset_size.image_mapped_items, 180);
  assert.equal(acceptance.dataset_subset_size.vastu_rules, 30);
  assert.equal(acceptance.dataset_subset_size.evaluation_briefs, 10);
});

test("T22 acceptance run verifies full design journey and revision", () => {
  assert.equal(acceptance.checks.first_design_status, "passed");
  assert.equal(acceptance.checks.revision_status, "passed");
  assert.equal(acceptance.checks.revision_design_id_persisted, true);
  assert.ok(acceptance.checks.attempt_log_states.includes("planning"));
  assert.ok(acceptance.checks.attempt_log_states.includes("designing"));
  assert.ok(acceptance.checks.attempt_log_states.includes("grounding"));
  assert.ok(acceptance.checks.corrected_item_list_count > 0);
  assert.equal(acceptance.checks.selected_total_matches_items, true);
  assert.equal(acceptance.checks.budget_status, "pass");
  assert.notEqual(acceptance.checks.vastu_status, "skipped");
  assert.equal(acceptance.checks.export_brief_loaded, true);
  assert.equal(acceptance.checks.metrics_available, true);
});

test("T22 screenshots, PDF, and demo script are present", () => {
  assert.equal(acceptance.browser_evidence.status, "pass");
  assert.equal(acceptance.browser_evidence.images_loaded, true);
  assert.equal(acceptance.browser_evidence.export_contains_required_sections, true);
  for (const path of [...acceptance.browser_evidence.screenshots, acceptance.browser_evidence.pdf]) {
    assert.equal(existsSync(path), true, path);
    assert.ok(statSync(path).size > 1000, path);
  }
  assert.match(demoScript, /Demo Brief/);
  assert.match(demoScript, /npm run demo:acceptance/);
  assert.match(demoScript, /artifacts\/demo\/acceptance_run\.json/);
  assert.match(demoScript, /artifacts\/metrics\/eval_summary_table\.md/);
});
