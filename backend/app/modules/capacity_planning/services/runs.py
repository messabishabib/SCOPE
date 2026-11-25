from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from ..optimization.deterministic.solver import solve
from ..optimization.stochastic.solver import solve_uncertainty
from ..schemas import OptimizationRequest, OptimizationRun, Project
from .repository import repository

executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="capacity-solver")


def start_run(project: Project, request: OptimizationRequest) -> OptimizationRun:
    scenario = next((s for s in project.scenarios if s.id == request.scenario_id), None)
    if request.scenario_id and not scenario:
        raise ValueError("Scenario does not belong to this project")
    run = OptimizationRun(project_id=project.id, scenario_id=request.scenario_id, mode=request.mode,
                          input_snapshot=project.model_dump(mode="json"))
    repository.save_run(run)

    def work() -> None:
        active = repository.get_run(run.id)
        active.status = "running"
        repository.save_run(active)
        try:
            active.result = (solve(project, scenario, request.time_limit_seconds) if request.mode.value == "deterministic"
                             else solve_uncertainty(project, request.mode, request.time_limit_seconds))
            active.status = active.result.status
        except Exception as exc:
            active.status = "failed"
            active.error = str(exc)
        active.completed_at = datetime.utcnow()
        repository.save_run(active)

    executor.submit(work)
    return run

