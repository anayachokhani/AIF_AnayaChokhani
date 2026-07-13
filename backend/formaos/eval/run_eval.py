from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from formaos.agents.graph_loop import AgentLoopResult, run_agent_loop
from formaos.agents.planner import PlannerClient
from formaos.contracts import RoomBrief
from formaos.room_state import brief_dimensions_cm


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BRIEFS_PATH = ROOT / "data/eval/test_briefs.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/metrics"


@dataclass
class DeterministicEvalPlannerClient(PlannerClient):
    brief: RoomBrief
    brief_id: str

    def complete(self, messages: list[dict[str, str]]) -> str:
        dims = brief_dimensions_cm(self.brief)
        categories = categories_for_brief(self.brief_id, self.brief)
        share = round(1 / len(categories), 4)
        payload = {
            "room_facts": {
                "room_type": self.brief.room_type,
                "width_cm": dims.width_cm,
                "depth_cm": dims.depth_cm,
                "budget_inr": self.brief.budget_inr,
                "style_words": self.brief.style_words,
            },
            "constraints": self.brief.constraints,
            "needs_list": [
                {
                    "category": category,
                    "purpose": f"{category} for {self.brief.room_type}",
                    "quantity": 1,
                    "priority": index + 1,
                    "budget_share": share,
                    "style_tags": self.brief.style_words,
                    "constraints": self.brief.constraints,
                }
                for index, category in enumerate(categories)
            ],
            "missing_questions": [],
        }
        return json.dumps(payload)


def categories_for_brief(brief_id: str, brief: RoomBrief) -> list[str]:
    if brief_id == "impossible_tiny_room_full_set":
        return ["sofa", "rug", "storage", "lamp"]
    if brief_id == "impossible_budget_bedroom":
        return ["bed", "storage", "table", "lamp"]
    if brief.room_type == "bedroom":
        return ["bed", "storage", "table", "lamp"]
    if brief.room_type == "study":
        return ["desk", "chair", "lamp", "storage"]
    return ["table", "rug", "lamp", "planter"]


def load_briefs(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text())


def brief_model(brief: dict[str, Any]) -> RoomBrief:
    payload = {key: value for key, value in brief.items() if key not in {"id", "evaluation_tags"}}
    return RoomBrief.model_validate(payload)


def item_row(item: dict[str, Any], slot_id: str, estimated: bool = False) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "category": item.get("product_type") or item.get("category"),
        "item_id": item.get("item_id"),
        "title": item.get("title"),
        "width_cm": item.get("width_cm"),
        "depth_cm": item.get("depth_cm"),
        "height_cm": item.get("height_cm"),
        "price_inr": item.get("price_inr"),
        "image_path": item.get("image_path"),
        "source_dataset": item.get("source_dataset", "ABO" if item.get("item_id") else "baseline_ungrounded"),
        "estimated": estimated,
    }


def formaos_output(brief_record: dict[str, Any]) -> dict[str, Any]:
    brief = brief_model(brief_record)
    client = DeterministicEvalPlannerClient(brief=brief, brief_id=brief_record["id"])
    try:
        result = run_agent_loop(brief, planner_client=client, max_retries=2)
    except Exception as exc:  # Keep failed eval rows structured instead of aborting the run.
        return {
            "brief_id": brief_record["id"],
            "system": "formaos",
            "status": "failed",
            "selected_items": [],
            "total_price_inr": 0,
            "fit_notes": [],
            "budget_notes": [],
            "sourceability_notes": [],
            "vastu_notes": [],
            "failure_reason": f"{exc.__class__.__name__}: {exc}",
        }
    return normalize_formaos_result(brief_record["id"], result)


def normalize_formaos_result(brief_id: str, result: AgentLoopResult) -> dict[str, Any]:
    grounded_slots = result.grounder_output.model_dump(mode="json")["grounded_slots"]
    selected_items = [
        item_row(slot["selected_item"], slot["slot"]["slot_id"], estimated=False)
        for slot in grounded_slots
        if slot.get("selected_item")
    ]
    failures = [slot["failure"] for slot in grounded_slots if slot.get("failure")]
    verdict = result.critic_verdict.model_dump(mode="json")
    failure_reason = "; ".join(failure["blocked_by"] for failure in failures)
    if result.status == "failed" and not failure_reason:
        failure_reason = "; ".join(verdict.get("repair_notes", []))
    return {
        "brief_id": brief_id,
        "system": "formaos",
        "status": result.status,
        "selected_items": selected_items,
        "total_price_inr": verdict["total_price_inr"],
        "fit_notes": verdict["fit"]["notes"],
        "budget_notes": verdict["budget"]["notes"],
        "sourceability_notes": verdict["sourceability"]["notes"],
        "vastu_notes": verdict["vastu"]["notes"],
        "failure_reason": failure_reason,
        "_checks": {
            "fit_status": verdict["fit"]["status"],
            "budget_status": verdict["budget"]["status"],
            "sourceability_status": verdict["sourceability"]["status"],
            "vastu_status": verdict["vastu"]["status"],
            "vastu_score": verdict["vastu_result"]["score"] if verdict.get("vastu_result") else None,
        },
    }


def baseline_output(brief_record: dict[str, Any]) -> dict[str, Any]:
    brief = brief_model(brief_record)
    dims = brief_dimensions_cm(brief)
    categories = categories_for_brief(brief_record["id"], brief)
    price_share = max(1, round(brief.budget_inr / len(categories)))
    selected = []
    for index, category in enumerate(categories):
        selected.append(
            {
                "slot_id": f"baseline_slot_{index + 1}_{category}",
                "category": category,
                "item_id": None,
                "title": f"Estimated {category}",
                "width_cm": round(min(dims.width_cm * 0.7, 220), 1),
                "depth_cm": round(min(dims.depth_cm * 0.55, 220), 1),
                "height_cm": 75 if category not in {"rug", "lamp"} else (1 if category == "rug" else 45),
                "price_inr": price_share,
                "image_path": None,
                "source_dataset": "baseline_ungrounded",
                "estimated": True,
            }
        )
    total = sum(int(item["price_inr"]) for item in selected)
    return {
        "brief_id": brief_record["id"],
        "system": "baseline_ungrounded",
        "status": "partial",
        "selected_items": selected,
        "total_price_inr": total,
        "fit_notes": ["Dimensions are estimates; no hard room or slot fit validation was run."],
        "budget_notes": ["Prices are estimates; no catalogue price validation was run."],
        "sourceability_notes": ["No selected item maps to a curated catalogue item_id."],
        "vastu_notes": ["No deterministic Vastu rule execution was run." if brief.vastu_enabled else "Vastu not requested."],
        "failure_reason": "ungrounded baseline output",
        "_checks": {
            "fit_status": "fail",
            "budget_status": "pass" if total <= brief.budget_inr else "fail",
            "sourceability_status": "fail",
            "vastu_status": "fail" if brief.vastu_enabled else "skipped",
            "vastu_score": None,
        },
    }


def metric_row(brief_record: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    checks = output["_checks"]
    selected = output["selected_items"]
    sourceable = sum(1 for item in selected if item.get("item_id"))
    return {
        "brief_id": brief_record["id"],
        "system": output["system"],
        "status": output["status"],
        "selected_item_count": len(selected),
        "fit_pass": checks["fit_status"] == "pass",
        "budget_pass": checks["budget_status"] == "pass",
        "sourceable_items": sourceable,
        "sourceability_rate": round(sourceable / len(selected), 4) if selected else 0,
        "vastu_applicable": bool(brief_record["vastu_enabled"]),
        "vastu_pass_or_warn": checks["vastu_status"] in {"pass", "warn", "skipped"} if brief_record["vastu_enabled"] else None,
        "vastu_score": checks["vastu_score"],
        "total_price_inr": output["total_price_inr"],
        "budget_inr": brief_record["budget_inr"],
        "failure_reason": output["failure_reason"],
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    systems = sorted({row["system"] for row in rows})
    summary: dict[str, Any] = {"systems": {}, "metric_definitions": "data/eval/metric_definitions.json"}
    for system in systems:
        system_rows = [row for row in rows if row["system"] == system]
        selected_total = sum(row["selected_item_count"] for row in system_rows)
        sourceable_total = sum(row["sourceable_items"] for row in system_rows)
        vastu_rows = [row for row in system_rows if row["vastu_applicable"]]
        summary["systems"][system] = {
            "briefs_evaluated": len(system_rows),
            "passed_designs": sum(1 for row in system_rows if row["status"] == "passed"),
            "fit_rate": round(sum(1 for row in system_rows if row["fit_pass"]) / len(system_rows), 4),
            "budget_accuracy": round(sum(1 for row in system_rows if row["budget_pass"]) / len(system_rows), 4),
            "sourceability": round(sourceable_total / selected_total, 4) if selected_total else 0,
            "vastu_compliance": round(sum(1 for row in vastu_rows if row["vastu_pass_or_warn"]) / len(vastu_rows), 4) if vastu_rows else None,
        }
    return summary


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_summary_table(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "| System | Briefs | Passed designs | Fit rate | Budget accuracy | Sourceability | Vastu compliance |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for system, row in summary["systems"].items():
        lines.append(
            "| {system} | {briefs_evaluated} | {passed_designs} | {fit_rate:.2%} | {budget_accuracy:.2%} | {sourceability:.2%} | {vastu} |".format(
                system=system,
                briefs_evaluated=row["briefs_evaluated"],
                passed_designs=row["passed_designs"],
                fit_rate=row["fit_rate"],
                budget_accuracy=row["budget_accuracy"],
                sourceability=row["sourceability"],
                vastu="n/a" if row["vastu_compliance"] is None else f"{row['vastu_compliance']:.2%}",
            )
        )
    path.write_text("\n".join(lines) + "\n")


def run_eval(briefs_path: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    briefs = load_briefs(briefs_path)
    raw_outputs: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for brief_record in briefs:
        for output in (formaos_output(brief_record), baseline_output(brief_record)):
            raw_outputs.append({key: value for key, value in output.items() if key != "_checks"})
            rows.append(metric_row(brief_record, output))
    summary = summarize(rows)
    failure_examples = [
        {
            "brief_id": row["brief_id"],
            "system": row["system"],
            "status": row["status"],
            "failure_reason": row["failure_reason"],
        }
        for row in rows
        if row["failure_reason"]
    ]
    write_json(output_dir / "eval_raw_outputs.json", raw_outputs)
    write_json(output_dir / "eval_metric_rows.json", rows)
    write_csv(output_dir / "eval_metric_rows.csv", rows)
    write_json(output_dir / "eval_summary.json", summary)
    write_json(output_dir / "eval_failure_examples.json", failure_examples)
    write_summary_table(output_dir / "eval_summary_table.md", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--briefs", type=Path, default=DEFAULT_BRIEFS_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    summary = run_eval(args.briefs, args.output_dir)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
