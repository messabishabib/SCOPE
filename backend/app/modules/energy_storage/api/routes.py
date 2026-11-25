from fastapi import APIRouter, HTTPException, status

from ..schemas import EnergyOptimizationRequest, EnergyOptimizationRun, EnergyProject, EnergyProjectCreate, EnergySimulationRequest, EnergySimulationRun
from ..services.repository import energy_repository
from ..services.runs import start_energy_run
from ..services.simulation import start_simulation_run

router = APIRouter(prefix="/api/energy", tags=["Energy storage"])


@router.get("/projects", response_model=list[EnergyProject])
def list_energy_projects():
    return energy_repository.list_projects()


@router.post("/projects", response_model=EnergyProject, status_code=status.HTTP_201_CREATED)
def create_energy_project(payload: EnergyProjectCreate):
    return energy_repository.save_project(EnergyProject(**payload.model_dump()))


@router.get("/projects/{project_id}", response_model=EnergyProject)
def get_energy_project(project_id: str):
    project = energy_repository.get_project(project_id)
    if not project:
        raise HTTPException(404, "Energy project not found")
    return project


@router.put("/projects/{project_id}", response_model=EnergyProject)
def update_energy_project(project_id: str, payload: EnergyProjectCreate):
    current = energy_repository.get_project(project_id)
    if not current:
        raise HTTPException(404, "Energy project not found")
    return energy_repository.save_project(EnergyProject(id=project_id, created_at=current.created_at, **payload.model_dump()))


@router.post("/projects/{project_id}/runs", response_model=EnergyOptimizationRun, status_code=status.HTTP_202_ACCEPTED)
def optimize_energy_project(project_id: str, request: EnergyOptimizationRequest):
    project = energy_repository.get_project(project_id)
    if not project:
        raise HTTPException(404, "Energy project not found")
    try:
        return start_energy_run(project, request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/runs/{run_id}", response_model=EnergyOptimizationRun)
def get_energy_run(run_id: str):
    run = energy_repository.get_run(run_id)
    if not run:
        raise HTTPException(404, "Energy optimization run not found")
    return run


@router.post("/projects/{project_id}/simulations", response_model=EnergySimulationRun, status_code=status.HTTP_202_ACCEPTED)
def simulate_energy_project(project_id: str, request: EnergySimulationRequest):
    project = energy_repository.get_project(project_id)
    if not project:
        raise HTTPException(404, "Energy project not found")
    try:
        return start_simulation_run(project, request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/simulations/{run_id}", response_model=EnergySimulationRun)
def get_energy_simulation(run_id: str):
    run = energy_repository.get_simulation(run_id)
    if not run:
        raise HTTPException(404, "Energy simulation run not found")
    return run

