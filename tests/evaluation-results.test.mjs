import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const summary = JSON.parse(readFileSync("artifacts/metrics/eval_summary.json", "utf8"));
const rows = JSON.parse(readFileSync("artifacts/metrics/eval_metric_rows.json", "utf8"));
const rawOutputs = JSON.parse(readFileSync("artifacts/metrics/eval_raw_outputs.json", "utf8"));
const failures = JSON.parse(readFileSync("artifacts/metrics/eval_failure_examples.json", "utf8"));
const table = readFileSync("artifacts/metrics/eval_summary_table.md", "utf8");
const runner = readFileSync("backend/formaos/eval/run_eval.py", "utf8");

test("T21 evaluation runner and artifacts exist", () => {
  for (const path of [
    "backend/formaos/eval/run_eval.py",
    "artifacts/metrics/eval_raw_outputs.json",
    "artifacts/metrics/eval_metric_rows.json",
    "artifacts/metrics/eval_metric_rows.csv",
    "artifacts/metrics/eval_summary.json",
    "artifacts/metrics/eval_summary_table.md",
    "artifacts/metrics/eval_failure_examples.json",
  ]) {
    assert.equal(existsSync(path), true, path);
  }
  assert.match(runner, /run_agent_loop/);
  assert.match(runner, /baseline_output/);
  assert.match(runner, /DeterministicEvalPlannerClient/);
});

test("T21 metrics cover all 10 briefs for FormaOS and baseline", () => {
  assert.equal(rawOutputs.length, 20);
  assert.equal(rows.length, 20);
  assert.equal(rows.filter((row) => row.system === "formaos").length, 10);
  assert.equal(rows.filter((row) => row.system === "baseline_ungrounded").length, 10);

  for (const row of rows) {
    for (const field of ["brief_id", "system", "status", "fit_pass", "budget_pass", "sourceability_rate", "total_price_inr", "budget_inr"]) {
      assert.ok(field in row, `${row.brief_id} ${row.system} missing ${field}`);
    }
  }
});

test("T21 summary compares required metrics", () => {
  assert.deepEqual(Object.keys(summary.systems).sort(), ["baseline_ungrounded", "formaos"]);
  for (const system of Object.values(summary.systems)) {
    for (const metric of ["briefs_evaluated", "fit_rate", "budget_accuracy", "sourceability", "vastu_compliance"]) {
      assert.ok(metric in system, metric);
    }
    assert.equal(system.briefs_evaluated, 10);
  }
  assert.equal(summary.systems.formaos.sourceability, 1);
  assert.equal(summary.systems.baseline_ungrounded.sourceability, 0);
  assert.match(table, /Fit rate/);
  assert.match(table, /Budget accuracy/);
  assert.match(table, /Sourceability/);
  assert.match(table, /Vastu compliance/);
});

test("T21 raw outputs preserve baseline/sourceability distinction and failure evidence", () => {
  const baselineItems = rawOutputs
    .filter((output) => output.system === "baseline_ungrounded")
    .flatMap((output) => output.selected_items);
  assert.ok(baselineItems.length > 0);
  assert.ok(baselineItems.every((item) => item.item_id === null));
  assert.ok(baselineItems.every((item) => item.image_path === null));
  assert.ok(baselineItems.every((item) => item.estimated === true));

  const formaosItems = rawOutputs
    .filter((output) => output.system === "formaos")
    .flatMap((output) => output.selected_items);
  assert.ok(formaosItems.some((item) => item.item_id));

  assert.ok(failures.length >= 10);
  assert.ok(failures.some((failure) => failure.system === "formaos"));
  assert.ok(failures.some((failure) => failure.brief_id.includes("impossible")));
});
