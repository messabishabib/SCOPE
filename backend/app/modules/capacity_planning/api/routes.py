import csv
import io

from fastapi import APIRouter, HTTPException, Response, status

from ....core.identifiers import uid
from ..schemas import OptimizationRequest, OptimizationRun, PlanComparison, Project, ProjectCreate, Scenario, ScenarioDuplicate
from ..services.repository import repository
from ..services.runs import start_run

router = APIRouter(prefix="/api")


@router.get("/projects", response_model=list[Project])
def list_projects():
    return repository.list_projects()


@router.post("/projects", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate):
    return repository.save_project(Project(**payload.model_dump()))


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str):
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.put("/projects/{project_id}", response_model=Project)
def update_project(project_id: str, payload: ProjectCreate):
    old = repository.get_project(project_id)
    if not old:
        raise HTTPException(404, "Project not found")
    return repository.save_project(Project(id=project_id, created_at=old.created_at, **payload.model_dump()))


@router.post("/projects/{project_id}/scenarios/{scenario_id}/duplicate", response_model=Scenario, status_code=status.HTTP_201_CREATED)
def duplicate_scenario(project_id: str, scenario_id: str, payload: ScenarioDuplicate):
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    source = next((s for s in project.scenarios if s.id == scenario_id), None)
    if not source:
        raise HTTPException(404, "Scenario not found")
    duplicate = source.model_copy(update={"id": uid(), "name": payload.name, "probability": None}, deep=True)
    project.scenarios.append(duplicate)
    repository.save_project(project)
    return duplicate


@router.put("/projects/{project_id}/scenarios/{scenario_id}", response_model=Scenario)
def update_scenario(project_id: str, scenario_id: str, payload: Scenario):
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    index = next((i for i, s in enumerate(project.scenarios) if s.id == scenario_id), None)
    if index is None:
        raise HTTPException(404, "Scenario not found")
    if payload.id != scenario_id:
        raise HTTPException(422, "Scenario ID cannot be changed")
    project.scenarios[index] = payload
    repository.save_project(project)
    return payload


@router.post("/projects/{project_id}/runs", response_model=OptimizationRun, status_code=status.HTTP_202_ACCEPTED)
def optimize(project_id: str, request: OptimizationRequest):
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    try:
        return start_run(project, request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/projects/{project_id}/runs", response_model=list[OptimizationRun])
def list_runs(project_id: str):
    return repository.list_runs(project_id)


@router.get("/runs/{run_id}", response_model=OptimizationRun)
def get_run(run_id: str):
    run = repository.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/runs/compare/{baseline_run_id}/{candidate_run_id}", response_model=PlanComparison)
def compare_runs(baseline_run_id: str, candidate_run_id: str):
    baseline = repository.get_run(baseline_run_id)
    candidate = repository.get_run(candidate_run_id)
    if not baseline or not baseline.result or not candidate or not candidate.result:
        raise HTTPException(404, "Both completed runs are required")
    if baseline.project_id != candidate.project_id:
        raise HTTPException(422, "Runs must belong to the same project")
    base_cost, candidate_cost = baseline.result.costs.total, candidate.result.costs.total
    base_unmet = sum(x.unmet for x in baseline.result.demands)
    candidate_unmet = sum(x.unmet for x in candidate.result.demands)
    base_expansion = sum(x.activated_capacity for x in baseline.result.capacities)
    candidate_expansion = sum(x.activated_capacity for x in candidate.result.capacities)
    return PlanComparison(
        baseline_run_id=baseline.id, candidate_run_id=candidate.id,
        total_cost_change=candidate_cost - base_cost,
        total_cost_change_percent=((candidate_cost - base_cost) / base_cost * 100) if base_cost else None,
        service_rate_change=candidate.result.service_rate - baseline.result.service_rate,
        unmet_demand_change=candidate_unmet - base_unmet,
        activated_capacity_change=candidate_expansion - base_expansion,
    )


@router.get("/runs/{run_id}/export.csv")
def export_run(run_id: str):
    run = repository.get_run(run_id)
    if not run or not run.result:
        raise HTTPException(404, "Completed run not found")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["resource_id", "demand_id", "period", "quantity", "unit_cost"])
    for row in run.result.allocations:
        writer.writerow([row.resource_id, row.demand_id, row.period + 1, row.quantity, row.unit_cost])
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="plan-{run_id}.csv"'})

