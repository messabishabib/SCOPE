"""Closed-loop execution of energy-storage optimization policies.

The optimizer proposes one action from forecasts.  This module applies only that
first action to realized conditions, updates the physical state, and repeats.
Keeping execution separate from model construction makes forecast decisions and
realized performance easy to inspect independently.
"""

from datetime import datetime

from ..optimization.solve import solve as solve_deterministic
from ..optimization.stochastic.solve import solve as solve_stochastic
from ..schemas import (
    EnergyCostBreakdown,
    EnergyOptimizationRequest,
    EnergyPlanningMode,
    EnergyProject,
    EnergyScenario,
    EnergySimulationPolicyResult,
    EnergySimulationRequest,
    EnergySimulationResult,
    EnergySimulationRun,
    EnergySimulationStep,
    StorageSimulationStep,
)
from .repository import energy_repository
from .runs import energy_executor, prepare_rolling_project, resolve_current_energies


def simulate(project: EnergyProject, request: EnergySimulationRequest) -> EnergySimulationResult:
    """Compare policies on exactly the same realized scenario path."""
    scenario = _select_realized_scenario(project, request.realized_scenario_id)
    start, end, initial_energies = _validate_and_resolve_horizon(project, request)

    policy_results = [
        _simulate_policy(project, scenario, policy, request, start, end, initial_energies)
        for policy in request.policies
    ]
    statuses = {result.status for result in policy_results}
    overall_status = "optimal" if statuses == {"optimal"} else "feasible" if statuses <= {"optimal", "feasible"} else "failed"
    return EnergySimulationResult(
        status=overall_status,
        realized_scenario_id=scenario.id,
        realized_scenario_name=scenario.name,
        start_period=start,
        horizon_periods=end - start,
        policy_results=policy_results,
        diagnostics={
            "execution": "receding horizon: optimize, apply first action, reveal realization, update state",
            "same_realized_path_for_all_policies": True,
            "grid_assumption": "unlimited import/export; therefore no load shedding occurs in simulation v1",
        },
    )


def _simulate_policy(
    project: EnergyProject,
    scenario: EnergyScenario,
    policy: EnergyPlanningMode,
    request: EnergySimulationRequest,
    start: int,
    end: int,
    initial_energies: dict[str, float],
) -> EnergySimulationPolicyResult:
    if policy == EnergyPlanningMode.stochastic and not project.scenarios:
        raise ValueError("the stochastic policy requires at least one configured energy scenario")

    stored_energies = dict(initial_energies)
    steps: list[EnergySimulationStep] = []
    for period in range(start, end):
        planning_request = EnergyOptimizationRequest(
            mode=policy,
            current_period=period,
            current_energy_mwh_by_storage=stored_energies,
            lookahead_periods=min(request.lookahead_periods, project.number_of_periods - period),
            commitment_periods=request.commitment_periods,
            time_limit_seconds=request.time_limit_seconds,
        )
        planning_project = prepare_rolling_project(project, planning_request)
        solution = (
            solve_stochastic(planning_project, request.time_limit_seconds, request.commitment_periods)
            if policy == EnergyPlanningMode.stochastic
            else solve_deterministic(planning_project, request.time_limit_seconds)
        )
        if not solution.periods:
            raise RuntimeError(f"{policy.value} policy returned no action at period {period}: {solution.status}")

        planned = solution.periods[0]
        step = _execute_realized_step(
            project=project,
            scenario=scenario,
            period=period,
            stored_energies=stored_energies,
            planned_charge_power_mw={x.storage_id: x.charge_power_mw for x in planned.storage_dispatches},
            planned_discharge_power_mw={x.storage_id: x.discharge_power_mw for x in planned.storage_dispatches},
            solve_status=solution.status,
            solver_runtime_seconds=solution.solver_runtime_seconds,
        )
        steps.append(step)
        stored_energies = {x.storage_id: x.stored_energy_end_mwh for x in step.storage_steps}

    return _summarize_policy(project, policy, steps, stored_energies)


def _execute_realized_step(
    project: EnergyProject,
    scenario: EnergyScenario,
    period: int,
    stored_energies: dict[str, float],
    planned_charge_power_mw: dict[str, float],
    planned_discharge_power_mw: dict[str, float],
    solve_status: str,
    solver_runtime_seconds: float,
) -> EnergySimulationStep:
    """Apply a planned physical action to one newly observed period."""
    hours = project.interval_hours
    demand = project.demand_mwh[period] * scenario.demand_multiplier[period]
    renewable = project.renewable_generation_mwh[period] * scenario.renewable_multiplier[period]
    import_price = project.grid_import_price_per_mwh[period] * scenario.price_multiplier[period]
    export_price = project.grid_export_price_per_mwh[period] * scenario.price_multiplier[period]
    storage_steps = []
    for index, storage in enumerate(project.storages):
        inflow = scenario.natural_inflow_mwh_by_storage.get(storage.id, scenario.natural_inflow_mwh if index == 0 else [0.0] * project.number_of_periods)[period]
        stored_energy = stored_energies[storage.id]
        planned_charge = planned_charge_power_mw.get(storage.id, 0.0)
        planned_discharge = planned_discharge_power_mw.get(storage.id, 0.0)
        charge = min(max(planned_charge, 0.0), storage.maximum_charge_power_mw)
        discharge_limit = max(0.0, (stored_energy + storage.charge_efficiency * charge * hours + inflow - storage.minimum_energy_mwh) * storage.discharge_efficiency / hours)
        discharge = min(max(planned_discharge, 0.0), storage.maximum_discharge_power_mw, discharge_limit)
        unconstrained_end = stored_energy + storage.charge_efficiency * charge * hours - discharge * hours / storage.discharge_efficiency + inflow
        spill = max(0.0, unconstrained_end - storage.energy_capacity_mwh)
        stored_energy_end = min(storage.energy_capacity_mwh, max(storage.minimum_energy_mwh, unconstrained_end - spill))
        tolerance = 1e-6
        storage_steps.append(StorageSimulationStep(storage_id=storage.id, storage_name=storage.name, realized_inflow_mwh=inflow,
            planned_charge_power_mw=planned_charge, planned_discharge_power_mw=planned_discharge,
            applied_charge_power_mw=charge, applied_discharge_power_mw=discharge,
            action_adjusted=abs(charge-planned_charge)>tolerance or abs(discharge-planned_discharge)>tolerance,
            stored_energy_start_mwh=stored_energy, stored_energy_end_mwh=stored_energy_end, spilled_inflow_mwh=spill))
    total_charge = sum(x.applied_charge_power_mw for x in storage_steps)
    total_discharge = sum(x.applied_discharge_power_mw for x in storage_steps)
    net_grid_need = demand + total_charge * hours - renewable - total_discharge * hours
    grid_import = max(0.0, net_grid_need)
    grid_export = max(0.0, -net_grid_need)
    period_cost = (
        grid_import * import_price
        - grid_export * export_price
        + sum(x.applied_charge_power_mw * hours * storage.variable_charge_cost_per_mwh + x.applied_discharge_power_mw * hours * storage.variable_discharge_cost_per_mwh for x, storage in zip(storage_steps, project.storages))
        + sum(x.spilled_inflow_mwh for x in storage_steps) * project.spill_penalty_per_mwh
    )
    return EnergySimulationStep(
        period=period,
        solve_status=solve_status,
        solver_runtime_seconds=solver_runtime_seconds,
        realized_demand_mwh=demand,
        realized_renewable_mwh=renewable,
        realized_import_price_per_mwh=import_price,
        realized_export_price_per_mwh=export_price,
        realized_inflow_mwh=sum(x.realized_inflow_mwh for x in storage_steps),
        planned_charge_power_mw=sum(x.planned_charge_power_mw for x in storage_steps),
        planned_discharge_power_mw=sum(x.planned_discharge_power_mw for x in storage_steps),
        applied_charge_power_mw=total_charge,
        applied_discharge_power_mw=total_discharge,
        action_adjusted=any(x.action_adjusted for x in storage_steps),
        stored_energy_start_mwh=sum(x.stored_energy_start_mwh for x in storage_steps),
        stored_energy_end_mwh=sum(x.stored_energy_end_mwh for x in storage_steps),
        spilled_inflow_mwh=sum(x.spilled_inflow_mwh for x in storage_steps),
        grid_import_mwh=grid_import,
        grid_export_mwh=grid_export,
        period_cost=period_cost,
        storage_steps=storage_steps,
    )


def _summarize_policy(project, policy, steps, final_energies):
    hours = project.interval_hours
    grid_import_cost = sum(step.grid_import_mwh * step.realized_import_price_per_mwh for step in steps)
    export_revenue = sum(step.grid_export_mwh * step.realized_export_price_per_mwh for step in steps)
    storage_map = {storage.id: storage for storage in project.storages}
    charging_cost = sum(asset.applied_charge_power_mw * hours * storage_map[asset.storage_id].variable_charge_cost_per_mwh for step in steps for asset in step.storage_steps)
    discharging_cost = sum(asset.applied_discharge_power_mw * hours * storage_map[asset.storage_id].variable_discharge_cost_per_mwh for step in steps for asset in step.storage_steps)
    spillage_cost = sum(step.spilled_inflow_mwh for step in steps) * project.spill_penalty_per_mwh
    # Value remaining water at the evaluation boundary so a policy cannot look
    # artificially cheap merely by emptying the reservoir before simulation ends.
    terminal_value = sum(final_energies.values()) * project.terminal_energy_value_per_mwh
    total = grid_import_cost - export_revenue + charging_cost + discharging_cost + spillage_cost - terminal_value
    statuses = {step.solve_status for step in steps}
    status = "optimal" if statuses == {"optimal"} else "feasible" if statuses <= {"optimal", "feasible"} else "failed"
    return EnergySimulationPolicyResult(
        planning_mode=policy,
        status=status,
        steps=steps,
        costs=EnergyCostBreakdown(
            grid_import=grid_import_cost,
            grid_export_revenue=export_revenue,
            charging=charging_cost,
            discharging=discharging_cost,
            shortage=0.0,
            spillage=spillage_cost,
            terminal_value=terminal_value,
            total=total,
        ),
        total_grid_import_mwh=sum(step.grid_import_mwh for step in steps),
        total_grid_export_mwh=sum(step.grid_export_mwh for step in steps),
        total_charge_mwh=sum(step.applied_charge_power_mw * hours for step in steps),
        total_discharge_mwh=sum(step.applied_discharge_power_mw * hours for step in steps),
        total_spilled_inflow_mwh=sum(step.spilled_inflow_mwh for step in steps),
        final_energy_mwh=sum(final_energies.values()),
        final_energy_mwh_by_storage=final_energies,
        solver_runtime_seconds=sum(step.solver_runtime_seconds for step in steps),
    )


def _select_realized_scenario(project: EnergyProject, scenario_id: str | None) -> EnergyScenario:
    if project.scenarios:
        selected_id = scenario_id or project.scenarios[0].id
        scenario = next((item for item in project.scenarios if item.id == selected_id), None)
        if scenario is None:
            raise ValueError("realized_scenario_id does not match a configured energy scenario")
        return scenario
    if scenario_id:
        raise ValueError("realized_scenario_id was supplied but the project has no scenarios")
    periods = project.number_of_periods
    return EnergyScenario(
        id="base-forecast",
        name="Base forecast",
        probability=1.0,
        demand_multiplier=[1.0] * periods,
        renewable_multiplier=[1.0] * periods,
        price_multiplier=[1.0] * periods,
        natural_inflow_mwh=[0.0] * periods,
    )


def _validate_and_resolve_horizon(project, request):
    if request.start_period >= project.number_of_periods:
        raise ValueError("start_period is outside the project horizon")
    end = min(project.number_of_periods, request.start_period + (request.horizon_periods or project.number_of_periods))
    initial_energies = resolve_current_energies(project, request.current_energy_mwh, request.current_energy_mwh_by_storage)
    return request.start_period, end, initial_energies


def start_simulation_run(project: EnergyProject, request: EnergySimulationRequest) -> EnergySimulationRun:
    """Persist and execute a potentially multi-solve simulation in the background."""
    _select_realized_scenario(project, request.realized_scenario_id)
    _validate_and_resolve_horizon(project, request)
    run = EnergySimulationRun(
        project_id=project.id,
        input_snapshot={"project": project.model_dump(mode="json"), "request": request.model_dump(mode="json")},
    )
    energy_repository.save_simulation(run)

    def work():
        active = energy_repository.get_simulation(run.id)
        active.status = "running"
        energy_repository.save_simulation(active)
        try:
            active.result = simulate(project, request)
            active.status = active.result.status
        except Exception as exc:
            active.status, active.error = "failed", str(exc)
        active.completed_at = datetime.utcnow()
        energy_repository.save_simulation(active)

    energy_executor.submit(work)
    return run
