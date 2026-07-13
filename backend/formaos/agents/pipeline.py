from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from formaos.agents.critic import CriticVerdict, critique_design
from formaos.agents.designer import DEFAULT_CATALOGUE_PATH, DesignerOutput, design_slots
from formaos.agents.grounder import DEFAULT_CHROMA_PATH, GrounderOutput, ground_design
from formaos.agents.planner import PlannerClient, PlannerOutput, plan_room
from formaos.contracts import RoomBrief


class PlannerDesignerResult(BaseModel):
    planner_output: PlannerOutput
    designer_output: DesignerOutput


class PlannerDesignerGrounderResult(BaseModel):
    planner_output: PlannerOutput
    designer_output: DesignerOutput
    grounder_output: GrounderOutput


class PlannerDesignerGrounderCriticResult(BaseModel):
    planner_output: PlannerOutput
    designer_output: DesignerOutput
    grounder_output: GrounderOutput
    critic_verdict: CriticVerdict


def run_planner_designer(
    brief: RoomBrief,
    *,
    planner_client: PlannerClient | None = None,
    catalogue_path: Path = DEFAULT_CATALOGUE_PATH,
    include_concept_prompt: bool = False,
) -> PlannerDesignerResult:
    planner_output = plan_room(brief, planner_client)
    designer_output = design_slots(
        brief,
        planner_output,
        catalogue_path=catalogue_path,
        include_concept_prompt=include_concept_prompt,
    )
    return PlannerDesignerResult(planner_output=planner_output, designer_output=designer_output)


def run_planner_designer_grounder(
    brief: RoomBrief,
    *,
    planner_client: PlannerClient | None = None,
    catalogue_path: Path = DEFAULT_CATALOGUE_PATH,
    chroma_path: Path = DEFAULT_CHROMA_PATH,
    include_concept_prompt: bool = False,
) -> PlannerDesignerGrounderResult:
    planner_designer = run_planner_designer(
        brief,
        planner_client=planner_client,
        catalogue_path=catalogue_path,
        include_concept_prompt=include_concept_prompt,
    )
    grounder_output = ground_design(
        brief,
        planner_designer.designer_output.slots,
        chroma_path=chroma_path,
        catalogue_path=catalogue_path,
    )
    return PlannerDesignerGrounderResult(
        planner_output=planner_designer.planner_output,
        designer_output=planner_designer.designer_output,
        grounder_output=grounder_output,
    )


def run_planner_designer_grounder_critic(
    brief: RoomBrief,
    *,
    planner_client: PlannerClient | None = None,
    catalogue_path: Path = DEFAULT_CATALOGUE_PATH,
    chroma_path: Path = DEFAULT_CHROMA_PATH,
    include_concept_prompt: bool = False,
) -> PlannerDesignerGrounderCriticResult:
    planner_designer_grounder = run_planner_designer_grounder(
        brief,
        planner_client=planner_client,
        catalogue_path=catalogue_path,
        chroma_path=chroma_path,
        include_concept_prompt=include_concept_prompt,
    )
    critic_verdict = critique_design(
        brief,
        planner_designer_grounder.grounder_output,
        catalogue_path=catalogue_path,
    )
    return PlannerDesignerGrounderCriticResult(
        planner_output=planner_designer_grounder.planner_output,
        designer_output=planner_designer_grounder.designer_output,
        grounder_output=planner_designer_grounder.grounder_output,
        critic_verdict=critic_verdict,
    )
