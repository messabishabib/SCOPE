from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from ..optimization.solve import solve as solve_deterministic
from ..optimization.stochastic.solve import solve as solve_stochastic
from ..schemas import EnergyOptimizationRequest, EnergyOptimizationRun, EnergyPlanningMode, EnergyProject, EnergyRecommendedAction, StorageRecommendedAction
from .repository import energy_repository

energy_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="energy-solver")


def start_energy_run(project: EnergyProject, request: EnergyOptimizationRequest) -> EnergyOptimizationRun:
    planning_project = prepare_rolling_project(project, request)
    run = EnergyOptimizationRun(project_id=project.id, input_snapshot={"project": planning_project.model_dump(mode="json"), "request": request.model_dump(mode="json")})
    energy_repository.save_run(run)

    def work():
        active = energy_repository.get_run(run.id)
        active.status = "running"
        energy_repository.save_run(active)
        try:
            active.result = (solve_stochastic(planning_project, request.time_limit_seconds, request.commitment_periods)
                             if request.mode == EnergyPlanningMode.stochastic else solve_deterministic(planning_project, request.time_limit_seconds))
            active.result.start_period = request.current_period
            if active.result.periods and active.result.recommended_action is None:
                first = active.result.periods[0]
                storage_actions = [StorageRecommendedAction(storage_id=x.storage_id, storage_name=x.storage_name, charge_power_mw=x.charge_power_mw, discharge_power_mw=x.discharge_power_mw) for x in first.storage_dispatches]
                details = [f"{x.storage_name}: charge {x.charge_power_mw:.1f} MW" if x.charge_power_mw > 1e-6 else f"{x.storage_name}: generate {x.discharge_power_mw:.1f} MW" if x.discharge_power_mw > 1e-6 else f"{x.storage_name}: hold" for x in storage_actions]
                active.result.recommended_action = EnergyRecommendedAction(period=request.current_period, charge_power_mw=first.charge_power_mw, discharge_power_mw=first.discharge_power_mw, explanation="; ".join(details) + ".", storage_actions=storage_actions)
            elif active.result.recommended_action:
                active.result.recommended_action.period = request.current_period
            active.status = active.result.status
        except Exception as exc:
            active.status, active.error = "failed", str(exc)
        active.completed_at = datetime.utcnow()
        energy_repository.save_run(active)

    energy_executor.submit(work)
    return run


def prepare_rolling_project(project: EnergyProject, request: EnergyOptimizationRequest) -> EnergyProject:
    if request.current_period >= project.number_of_periods:
        raise ValueError("current_period is outside the project horizon")
    current_energies = resolve_current_energies(project, request.current_energy_mwh, request.current_energy_mwh_by_storage)
    end = min(project.number_of_periods, request.current_period + (request.lookahead_periods or project.number_of_periods))
    start = request.current_period
    payload = project.model_dump(mode="json")
    payload["number_of_periods"] = end - start
    for field in ("demand_mwh", "renewable_generation_mwh", "grid_import_price_per_mwh", "grid_export_price_per_mwh"):
        payload[field] = payload[field][start:end]
    for storage_payload, storage in zip(payload["storages"], project.storages):
        storage_payload["initial_energy_mwh"] = current_energies[storage.id]
    # The original terminal target belongs to the end of the complete study.
    # An intermediate rolling window should not impose that target prematurely.
    if end < project.number_of_periods:
        for storage_payload, storage in zip(payload["storages"], project.storages):
            storage_payload["terminal_energy_minimum_mwh"] = storage.minimum_energy_mwh
    payload["scenarios"] = [{**scenario, "demand_multiplier":scenario["demand_multiplier"][start:end], "renewable_multiplier":scenario["renewable_multiplier"][start:end], "price_multiplier":scenario["price_multiplier"][start:end], "natural_inflow_mwh":scenario["natural_inflow_mwh"][start:end], "natural_inflow_mwh_by_storage":{storage_id: values[start:end] for storage_id, values in scenario.get("natural_inflow_mwh_by_storage", {}).items()}} for scenario in payload["scenarios"]]
    return EnergyProject.model_validate(payload)


def resolve_current_energies(project: EnergyProject, legacy_current_energy: float | None, current_by_storage: dict[str, float] | None) -> dict[str, float]:
    supplied = dict(current_by_storage or {})
    if legacy_current_energy is not None:
        supplied.setdefault(project.storages[0].id, legacy_current_energy)
    unknown = set(supplied) - {storage.id for storage in project.storages}
    if unknown:
        raise ValueError(f"current energy references unknown storage IDs: {sorted(unknown)}")
    resolved = {storage.id: supplied.get(storage.id, storage.initial_energy_mwh) for storage in project.storages}
    for storage in project.storages:
        if not storage.minimum_energy_mwh <= resolved[storage.id] <= storage.energy_capacity_mwh:
            raise ValueError(f"current energy for storage {storage.id} must respect its bounds")
    return resolved

