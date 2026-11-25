from __future__ import annotations

from pyomo.environ import value

from ..schemas import EnergyProject


def validate_solution(model, data: EnergyProject, tolerance: float = 1e-5) -> dict:
    """Independently recompute the important business constraints from solved values."""
    balance_residuals, transition_residuals, simultaneous_operation, terminal_margins = [], [], [], []
    hours = data.interval_hours
    for t in range(data.number_of_periods):
        charge = sum(value(model.charge_power_mw[storage.id, t]) for storage in data.storages)
        discharge = sum(value(model.discharge_power_mw[storage.id, t]) for storage in data.storages)
        supply = data.renewable_generation_mwh[t] - value(model.renewable_curtailment_mwh[t]) + value(model.grid_import_mwh[t]) + discharge * hours + value(model.unserved_energy_mwh[t])
        use = data.demand_mwh[t] + charge * hours + value(model.grid_export_mwh[t])
        balance_residuals.append(abs(supply - use))
        for storage in data.storages:
            asset_charge = value(model.charge_power_mw[storage.id, t])
            asset_discharge = value(model.discharge_power_mw[storage.id, t])
            expected_end = value(model.stored_energy_mwh[storage.id, t]) + storage.charge_efficiency * asset_charge * hours - asset_discharge * hours / storage.discharge_efficiency
            transition_residuals.append(abs(value(model.stored_energy_mwh[storage.id, t + 1]) - expected_end))
            simultaneous_operation.append(min(asset_charge, asset_discharge))
    max_balance = max(balance_residuals, default=0)
    max_transition = max(transition_residuals, default=0)
    max_simultaneous = max(simultaneous_operation, default=0)
    for storage in data.storages:
        terminal_margins.append(value(model.stored_energy_mwh[storage.id, data.number_of_periods]) - storage.terminal_energy_minimum_mwh)
    return {
        "solution_validated": max(max_balance, max_transition, max_simultaneous) <= tolerance and min(terminal_margins, default=0) >= -tolerance,
        "maximum_energy_balance_residual_mwh": max_balance,
        "maximum_storage_transition_residual_mwh": max_transition,
        "maximum_simultaneous_charge_discharge_mw": max_simultaneous,
        "minimum_terminal_requirement_margin_mwh": min(terminal_margins, default=0),
        "storage_count": len(data.storages),
    }

