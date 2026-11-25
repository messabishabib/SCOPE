from __future__ import annotations

from pyomo.environ import value

from ..schemas import EnergyProject


def validate_solution(model, data: EnergyProject, tolerance: float = 1e-5) -> dict:
    """Independently recompute the important business constraints from solved values."""
    balance_residuals, transition_residuals, simultaneous_operation, terminal_margins = [], [], [], []
    import_limit_violations, export_limit_violations = [], []
    hours = data.interval_hours
    for t in range(data.number_of_periods):
        charge = sum(value(model.charge_power_mw[storage.id, t]) for storage in data.storages)
        discharge = sum(value(model.discharge_power_mw[storage.id, t]) for storage in data.storages)
        supply = data.renewable_generation_mwh[t] - value(model.renewable_curtailment_mwh[t]) + value(model.grid_import_mwh[t]) + discharge * hours + value(model.unserved_energy_mwh[t])
        use = data.demand_mwh[t] + charge * hours + value(model.grid_export_mwh[t])
        balance_residuals.append(abs(supply - use))
        if data.grid_import_capacity_mw is not None:
            import_limit_violations.append(max(0.0, value(model.grid_import_mwh[t]) - data.grid_import_capacity_mw * hours))
        if data.grid_export_capacity_mw is not None:
            export_limit_violations.append(max(0.0, value(model.grid_export_mwh[t]) - data.grid_export_capacity_mw * hours))
        for storage in data.storages:
            asset_charge = value(model.charge_power_mw[storage.id, t])
            asset_discharge = value(model.discharge_power_mw[storage.id, t])
            expected_end = value(model.stored_energy_mwh[storage.id, t]) + storage.charge_efficiency * asset_charge * hours - asset_discharge * hours / storage.discharge_efficiency
            transition_residuals.append(abs(value(model.stored_energy_mwh[storage.id, t + 1]) - expected_end))
            simultaneous_operation.append(min(asset_charge, asset_discharge))
    max_balance = max(balance_residuals, default=0)
    max_transition = max(transition_residuals, default=0)
    max_simultaneous = max(simultaneous_operation, default=0)
    max_import_violation = max(import_limit_violations, default=0)
    max_export_violation = max(export_limit_violations, default=0)
    import_limit_mwh = None if data.grid_import_capacity_mw is None else data.grid_import_capacity_mw * hours
    export_limit_mwh = None if data.grid_export_capacity_mw is None else data.grid_export_capacity_mw * hours
    import_values = [value(model.grid_import_mwh[t]) for t in range(data.number_of_periods)]
    export_values = [value(model.grid_export_mwh[t]) for t in range(data.number_of_periods)]
    for storage in data.storages:
        terminal_margins.append(value(model.stored_energy_mwh[storage.id, data.number_of_periods]) - storage.terminal_energy_minimum_mwh)
    return {
        "solution_validated": max(max_balance, max_transition, max_simultaneous, max_import_violation, max_export_violation) <= tolerance and min(terminal_margins, default=0) >= -tolerance,
        "maximum_energy_balance_residual_mwh": max_balance,
        "maximum_storage_transition_residual_mwh": max_transition,
        "maximum_simultaneous_charge_discharge_mw": max_simultaneous,
        "minimum_terminal_requirement_margin_mwh": min(terminal_margins, default=0),
        "maximum_grid_import_limit_violation_mwh": max_import_violation,
        "maximum_grid_export_limit_violation_mwh": max_export_violation,
        "grid_import_binding_periods": 0 if import_limit_mwh is None else sum(abs(item - import_limit_mwh) <= tolerance for item in import_values),
        "grid_export_binding_periods": 0 if export_limit_mwh is None else sum(abs(item - export_limit_mwh) <= tolerance for item in export_values),
        "maximum_grid_import_utilization": None if not import_limit_mwh else max(import_values, default=0) / import_limit_mwh,
        "maximum_grid_export_utilization": None if not export_limit_mwh else max(export_values, default=0) / export_limit_mwh,
        "storage_count": len(data.storages),
    }

