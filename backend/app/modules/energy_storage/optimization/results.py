from pyomo.environ import value

from ..schemas import EnergyCostBreakdown, EnergyOptimizationResult, EnergyPeriodResult, EnergyProject, StoragePeriodResult
from .validation import validate_solution


def extract_result(model, data: EnergyProject, status: str, runtime: float, solver_diagnostics: dict) -> EnergyOptimizationResult:
    periods = []
    for t in range(data.number_of_periods):
        dispatches = [StoragePeriodResult(
            storage_id=storage.id, storage_name=storage.name,
            charge_power_mw=value(model.charge_power_mw[storage.id, t]),
            discharge_power_mw=value(model.discharge_power_mw[storage.id, t]),
            stored_energy_start_mwh=value(model.stored_energy_mwh[storage.id, t]),
            stored_energy_end_mwh=value(model.stored_energy_mwh[storage.id, t + 1]),
            spilled_inflow_mwh=0,
        ) for storage in data.storages]
        periods.append(EnergyPeriodResult(
            period=t, demand_mwh=data.demand_mwh[t], renewable_generation_mwh=data.renewable_generation_mwh[t],
            import_price_per_mwh=data.grid_import_price_per_mwh[t], charge_power_mw=sum(x.charge_power_mw for x in dispatches),
            discharge_power_mw=sum(x.discharge_power_mw for x in dispatches), stored_energy_start_mwh=sum(x.stored_energy_start_mwh for x in dispatches),
            stored_energy_end_mwh=sum(x.stored_energy_end_mwh for x in dispatches), grid_import_mwh=value(model.grid_import_mwh[t]),
            grid_export_mwh=value(model.grid_export_mwh[t]), unserved_energy_mwh=value(model.unserved_energy_mwh[t]),
            renewable_curtailment_mwh=value(model.renewable_curtailment_mwh[t]), spilled_inflow_mwh=0, storage_dispatches=dispatches))
    costs = EnergyCostBreakdown(
        grid_import=value(model.grid_import_cost), grid_export_revenue=value(model.grid_export_revenue),
        charging=value(model.charging_cost), discharging=value(model.discharging_cost), shortage=value(model.shortage_cost),
        spillage=0, terminal_value=value(model.terminal_storage_value), total=value(model.total_system_cost))
    curtailment = sum(p.renewable_curtailment_mwh for p in periods)
    diagnostics = {**solver_diagnostics, **validate_solution(model, data)}
    return EnergyOptimizationResult(status=status, objective_value=value(model.minimize_total_system_cost), solver_runtime_seconds=runtime,
        periods=periods, costs=costs, total_unserved_mwh=sum(p.unserved_energy_mwh for p in periods), renewable_curtailment_mwh=curtailment, total_spilled_inflow_mwh=0, diagnostics=diagnostics)

