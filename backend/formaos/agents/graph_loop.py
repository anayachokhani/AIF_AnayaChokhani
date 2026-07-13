from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from formaos.agents.critic import CriticVerdict, critique_design
from formaos.agents.designer import DEFAULT_CATALOGUE_PATH, DesignerOutput, design_slots
from formaos.agents.grounder import DEFAULT_CHROMA_PATH, GrounderOutput, ground_design
from formaos.agents.planner import PlannerClient, PlannerOutput, plan_room
from formaos.agents.reviser import ReviserOutput, revise_slots
from formaos.contracts import AttemptLogEntry, DesignSlot, ResponseState, RoomBrief


LoopStatus = Literal["passed", "failed"]


class AgentLoopState(TypedDict, total=False):
    brief: RoomBrief
    planner_output: PlannerOutput
    designer_output: DesignerOutput
    current_slots: list[DesignSlot]
    grounder_output: GrounderOutput
    critic_verdict: CriticVerdict
    attempt_log: list[AttemptLogEntry]
    retries_used: int
    max_retries: int
    final_status: LoopStatus


class AgentLoopResult(BaseModel):
    status: LoopStatus
    planner_output: PlannerOutput
    designer_output: DesignerOutput
    grounder_output: GrounderOutput
    critic_verdict: CriticVerdict
    attempt_log: list[AttemptLogEntry] = Field(default_factory=list)
    retries_used: int
    max_retries: int


def attempt_entry(
    attempt: int,
    state: ResponseState,
    notes: list[str],
    changed_slots: list[str] | None = None,
    changed_items: list[str] | None = None,
) -> AttemptLogEntry:
    return AttemptLogEntry(
        attempt=attempt,
        state=state,
        notes=notes,
        changed_slots=changed_slots or [],
        changed_items=changed_items or [],
    )


def build_agent_graph(
    *,
    planner_client: PlannerClient | None = None,
    catalogue_path: Path = DEFAULT_CATALOGUE_PATH,
    chroma_path: Path = DEFAULT_CHROMA_PATH,
    include_concept_prompt: bool = False,
):
    graph = StateGraph(AgentLoopState)

    def planner_node(state: AgentLoopState) -> dict[str, Any]:
        planner_output = plan_room(state["brief"], planner_client)
        return {
            "planner_output": planner_output,
            "attempt_log": [
                *state.get("attempt_log", []),
                attempt_entry(0, "planning", ["Planner produced room needs."]),
            ],
        }

    def designer_node(state: AgentLoopState) -> dict[str, Any]:
        designer_output = design_slots(
            state["brief"],
            state["planner_output"],
            catalogue_path=catalogue_path,
            include_concept_prompt=include_concept_prompt,
        )
        return {
            "designer_output": designer_output,
            "current_slots": designer_output.slots,
            "attempt_log": [
                *state.get("attempt_log", []),
                attempt_entry(0, "designing", [f"Designer produced {len(designer_output.slots)} slots."]),
            ],
        }

    def grounder_node(state: AgentLoopState) -> dict[str, Any]:
        grounder_output = ground_design(
            state["brief"],
            state["current_slots"],
            chroma_path=chroma_path,
            catalogue_path=catalogue_path,
        )
        attempt = state.get("retries_used", 0)
        return {
            "grounder_output": grounder_output,
            "attempt_log": [
                *state.get("attempt_log", []),
                attempt_entry(attempt, "grounding", [f"Grounder produced {len(grounder_output.grounded_slots)} grounded slots."]),
            ],
        }

    def critic_node(state: AgentLoopState) -> dict[str, Any]:
        verdict = critique_design(
            state["brief"],
            state["grounder_output"],
            catalogue_path=catalogue_path,
        )
        attempt = state.get("retries_used", 0)
        status: ResponseState = "passed" if verdict.passed else "failed"
        final_status: LoopStatus | None = None
        if verdict.passed:
            final_status = "passed"
        elif attempt >= state.get("max_retries", 2):
            final_status = "failed"
        update: dict[str, Any] = {
            "critic_verdict": verdict,
            "attempt_log": [
                *state.get("attempt_log", []),
                attempt_entry(attempt, status, verdict.repair_notes or ["Critic passed."]),
            ],
        }
        if final_status:
            update["final_status"] = final_status
        return update

    def reviser_node(state: AgentLoopState) -> dict[str, Any]:
        reviser_output: ReviserOutput = revise_slots(state["current_slots"], state["critic_verdict"])
        next_attempt = state.get("retries_used", 0) + 1
        return {
            "current_slots": reviser_output.slots,
            "retries_used": next_attempt,
            "attempt_log": [
                *state.get("attempt_log", []),
                attempt_entry(
                    next_attempt,
                    "revising",
                    reviser_output.notes,
                    reviser_output.changed_slots,
                    reviser_output.changed_items,
                ),
            ],
        }

    def after_critic(state: AgentLoopState) -> str:
        if state.get("final_status") in {"passed", "failed"}:
            return "end"
        return "revise"

    graph.add_node("planner", planner_node)
    graph.add_node("designer", designer_node)
    graph.add_node("grounder", grounder_node)
    graph.add_node("critic", critic_node)
    graph.add_node("reviser", reviser_node)
    graph.set_entry_point("planner")
    graph.add_edge("planner", "designer")
    graph.add_edge("designer", "grounder")
    graph.add_edge("grounder", "critic")
    graph.add_conditional_edges("critic", after_critic, {"revise": "reviser", "end": END})
    graph.add_edge("reviser", "grounder")
    return graph.compile()


def run_agent_loop(
    brief: RoomBrief,
    *,
    planner_client: PlannerClient | None = None,
    catalogue_path: Path = DEFAULT_CATALOGUE_PATH,
    chroma_path: Path = DEFAULT_CHROMA_PATH,
    max_retries: int = 2,
    include_concept_prompt: bool = False,
) -> AgentLoopResult:
    compiled = build_agent_graph(
        planner_client=planner_client,
        catalogue_path=catalogue_path,
        chroma_path=chroma_path,
        include_concept_prompt=include_concept_prompt,
    )
    state = compiled.invoke(
        {
            "brief": brief,
            "attempt_log": [],
            "retries_used": 0,
            "max_retries": max_retries,
        }
    )
    status = state.get("final_status", "failed")
    return AgentLoopResult(
        status=status,
        planner_output=state["planner_output"],
        designer_output=state["designer_output"],
        grounder_output=state["grounder_output"],
        critic_verdict=state["critic_verdict"],
        attempt_log=state.get("attempt_log", []),
        retries_used=state.get("retries_used", 0),
        max_retries=max_retries,
    )
