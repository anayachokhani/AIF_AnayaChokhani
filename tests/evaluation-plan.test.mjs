import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const briefs = JSON.parse(readFileSync("data/eval/test_briefs.json", "utf8"));
const baseline = JSON.parse(readFileSync("data/eval/baseline_definition.json", "utf8"));
const outputSchema = JSON.parse(readFileSync("data/eval/output_schema.json", "utf8"));
const metrics = JSON.parse(readFileSync("data/eval/metric_definitions.json", "utf8"));
const manifest = JSON.parse(readFileSync("data/eval/evaluation_manifest.json", "utf8"));
const report = JSON.parse(readFileSync("artifacts/metrics/evaluation_plan_validation.json", "utf8"));

const directions = new Set(["N", "NE", "E", "SE", "S", "SW", "W", "NW", "C"]);

test("T20 freezes exactly 10 valid evaluation briefs with required coverage", () => {
  assert.equal(briefs.length, 10);
  assert.equal(new Set(briefs.map((brief) => brief.id)).size, 10);

  for (const brief of briefs) {
    for (const field of ["id", "room_type", "width", "depth", "units", "budget_inr", "style_words", "constraints", "vastu_enabled", "evaluation_tags"]) {
      assert.ok(field in brief, `${brief.id} missing ${field}`);
    }
    assert.ok(["ft", "m", "cm"].includes(brief.units), brief.id);
    assert.ok(brief.width > 0 && brief.depth > 0, brief.id);
    assert.ok(brief.budget_inr > 0, brief.id);
    assert.ok(Array.isArray(brief.style_words), brief.id);
    assert.ok(Array.isArray(brief.constraints), brief.id);
    assert.ok(directions.has(brief.main_door_direction), brief.id);
    assert.ok(directions.has(brief.compass_direction), brief.id);
  }

  const tags = briefs.flatMap((brief) => brief.evaluation_tags);
  for (const required of ["living_room", "bedroom", "study", "small_budget", "large_budget", "vastu_on", "vastu_off", "impossible"]) {
    assert.ok(tags.includes(required), required);
  }
});

test("T20 defines baseline, common output schema, metrics, and frozen manifest", () => {
  assert.equal(baseline.baseline_id, "ungrounded_llm_item_list_v1");
  assert.equal(baseline.frozen, true);
  assert.ok(baseline.prohibited_capabilities.includes("catalogue item lookup"));
  assert.equal(baseline.output_policy.item_id, "must be null");

  assert.equal(outputSchema.schema_id, "formaos_eval_output_v1");
  assert.deepEqual(outputSchema.systems, ["formaos", "baseline_ungrounded"]);
  for (const field of ["brief_id", "system", "status", "selected_items", "total_price_inr"]) {
    assert.ok(outputSchema.required_top_level_fields.includes(field), field);
  }

  assert.equal(metrics.metrics.length, 4);
  assert.deepEqual(metrics.metrics.map((metric) => metric.id), ["fit_rate", "budget_accuracy", "sourceability", "vastu_compliance"]);
  assert.equal(manifest.frozen, true);
});

test("T20 validation report has no errors", () => {
  assert.equal(report.status, "pass");
  assert.equal(report.total_briefs, 10);
  assert.deepEqual(report.validation_errors, []);
  assert.equal(report.baseline_defined, true);
  assert.equal(report.common_output_schema_defined, true);
  assert.equal(report.frozen_before_metrics, true);
});
