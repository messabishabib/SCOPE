from pyomo.environ import value

from ...schemas import (
    EnergyCostBreakdown, EnergyOptimizationResult, EnergyPeriodResult,
    EnergyPlanningMode, EnergyRecommendedAction, EnergyScenarioPerformance,
    StoragePeriodResult, StorageRecommendedAction,
)
from .constraints import demand, export_price, import_price, renewable
from .validation import validate_solution


def extract_result(model, data, scenarios, probabilities, status, runtime, commitment_periods, solver_diagnostics):
    hours = data.interval_hours
    storages = {storage.id: storage for storage in data.storages}
    expected = lambda fn: sum(probabilities[s] * fn(s) for s in scenarios)
    periods = []
    for t in range(data.number_of_periods):
        dispatches = [StoragePeriodResult(
            storage_id=a, storage_name=storages[a].name,
            charge_power_mw=expected(lambda s, a=a: value(model.charge_power_mw[s, a, t])),
            discharge_power_mw=expected(lambda s, a=a: value(model.discharge_power_mw[s, a, t])),
            stored_energy_start_mwh=expected(lambda s, a=a: value(model.stored_energy_mwh[s, a, t])),
            stored_energy_end_mwh=expected(lambda s, a=a: value(model.stored_energy_mwh[s, a, t + 1])),
            spilled_inflow_mwh=expected(lambda s, a=a: value(model.spilled_inflow_mwh[s, a, t])),
        ) for a in model.STORAGES]
        periods.append(EnergyPeriodResult(
            period=t, demand_mwh=expected(lambda s: demand(data, scenarios[s], t)),
            renewable_generation_mwh=expected(lambda s: renewable(data, scenarios[s], t)),
            import_price_per_mwh=expected(lambda s: import_price(data, scenarios[s], t)),
            charge_power_mw=sum(x.charge_power_mw for x in dispatches), discharge_power_mw=sum(x.discharge_power_mw for x in dispatches),
            stored_energy_start_mwh=sum(x.stored_energy_start_mwh for x in dispatches), stored_energy_end_mwh=sum(x.stored_energy_end_mwh for x in dispatches),
            grid_import_mwh=expected(lambda s: value(model.grid_import_mwh[s, t])), grid_export_mwh=expected(lambda s: value(model.grid_export_mwh[s, t])),
            unserved_energy_mwh=expected(lambda s: value(model.unserved_energy_mwh[s, t])), renewable_curtailment_mwh=expected(lambda s: value(model.renewable_curtailment_mwh[s, t])),
            spilled_inflow_mwh=sum(x.spilled_inflow_mwh for x in dispatches),
            storage_dispatches=dispatches,
        ))
    grid_import = sum(probabilities[s] * sum(value(model.grid_import_mwh[s, t]) * import_price(data, scenarios[s], t) for t in model.PERIODS) for s in scenarios)
    export_revenue = sum(probabilities[s] * sum(value(model.grid_export_mwh[s, t]) * export_price(data, scenarios[s], t) for t in model.PERIODS) for s in scenarios)
    charging = sum(probabilities[s] * sum(value(model.charge_power_mw[s, a, t]) * hours * storages[a].variable_charge_cost_per_mwh for a in model.STORAGES for t in model.PERIODS) for s in scenarios)
    discharging = sum(probabilities[s] * sum(value(model.discharge_power_mw[s, a, t]) * hours * storages[a].variable_discharge_cost_per_mwh for a in model.STORAGES for t in model.PERIODS) for s in scenarios)
    shortage = sum(probabilities[s] * sum(value(model.unserved_energy_mwh[s, t]) * data.shortage_penalty_per_mwh for t in model.PERIODS) for s in scenarios)
    spillage = sum(probabilities[s] * sum(value(model.spilled_inflow_mwh[s, a, t]) * data.spill_penalty_per_mwh for a in model.STORAGES for t in model.PERIODS) for s in scenarios)
    terminal = sum(probabilities[s] * sum(value(model.stored_energy_mwh[s, a, data.number_of_periods]) for a in model.STORAGES) * data.terminal_energy_value_per_mwh for s in scenarios)
    costs = EnergyCostBreakdown(grid_import=grid_import, grid_export_revenue=export_revenue, charging=charging, discharging=discharging, shortage=shortage, spillage=spillage, terminal_value=terminal, total=grid_import-export_revenue+charging+discharging+shortage+spillage-terminal)
    performance = []
    for sid, scenario in scenarios.items():
        terminal_by_storage = {a: value(model.stored_energy_mwh[sid, a, data.number_of_periods]) for a in model.STORAGES}
        spill_by_storage = {a: sum(value(model.spilled_inflow_mwh[sid, a, t]) for t in model.PERIODS) for a in model.STORAGES}
        performance.append(EnergyScenarioPerformance(scenario_id=sid, scenario_name=scenario.name, probability=probabilities[sid], total_cost=value(model.scenario_cost[sid]), total_unserved_mwh=sum(value(model.unserved_energy_mwh[sid, t]) for t in model.PERIODS), total_spilled_inflow_mwh=sum(spill_by_storage.values()), spilled_inflow_mwh_by_storage=spill_by_storage, terminal_energy_mwh=sum(terminal_by_storage.values()), terminal_energy_mwh_by_storage=terminal_by_storage))
    reference = next(iter(scenarios))
    storage_actions = [StorageRecommendedAction(storage_id=a, storage_name=storages[a].name, charge_power_mw=value(model.charge_power_mw[reference, a, 0]), discharge_power_mw=value(model.discharge_power_mw[reference, a, 0])) for a in model.STORAGES]
    charge, discharge = sum(x.charge_power_mw for x in storage_actions), sum(x.discharge_power_mw for x in storage_actions)
    active = [f"{x.storage_name}: charge {x.charge_power_mw:.1f} MW" if x.charge_power_mw > 1e-6 else f"{x.storage_name}: generate {x.discharge_power_mw:.1f} MW" if x.discharge_power_mw > 1e-6 else f"{x.storage_name}: hold" for x in storage_actions]
    action = EnergyRecommendedAction(period=0, charge_power_mw=charge, discharge_power_mw=discharge, explanation="; ".join(active) + ". Shared across all scenarios.", storage_actions=storage_actions)
    diagnostics = {**solver_diagnostics, **validate_solution(model, data, scenarios, commitment_periods), "nonanticipativity":"physical charge/discharge commitments are shared by storage before scenario revelation", "spillage":"scenario-dependent recourse bounded by realized natural inflow", "probabilities_normalized":probabilities}
    return EnergyOptimizationResult(status=status, objective_value=value(model.minimize_expected_total_system_cost), solver_runtime_seconds=runtime, periods=periods, costs=costs, total_unserved_mwh=sum(p.unserved_energy_mwh for p in periods), renewable_curtailment_mwh=sum(p.renewable_curtailment_mwh for p in periods), total_spilled_inflow_mwh=sum(p.spilled_inflow_mwh for p in periods), planning_mode=EnergyPlanningMode.stochastic, recommended_action=action, scenario_performance=performance, diagnostics=diagnostics)
