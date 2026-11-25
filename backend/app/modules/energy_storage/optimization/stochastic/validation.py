from pyomo.environ import value

from .constraints import demand, natural_inflow, renewable


def validate_solution(model, data, scenarios, commitment_periods: int, tolerance: float = 1e-5):
    balance, transitions, simultaneous, nonanticipativity, spill_limits = [], [], [], [], []
    import_limits, export_limits = [], []
    storages = {storage.id: storage for storage in data.storages}
    first_storage_id, hours = data.storages[0].id, data.interval_hours
    scenario_ids, reference = list(scenarios), list(scenarios)[0]
    for sid, scenario in scenarios.items():
        for t in range(data.number_of_periods):
            total_charge = sum(value(model.charge_power_mw[sid, a, t]) for a in model.STORAGES)
            total_discharge = sum(value(model.discharge_power_mw[sid, a, t]) for a in model.STORAGES)
            supply = renewable(data, scenario, t) - value(model.renewable_curtailment_mwh[sid, t]) + value(model.grid_import_mwh[sid, t]) + total_discharge * hours + value(model.unserved_energy_mwh[sid, t])
            use = demand(data, scenario, t) + total_charge * hours + value(model.grid_export_mwh[sid, t])
            balance.append(abs(supply - use))
            if data.grid_import_capacity_mw is not None:
                import_limits.append(max(0.0, value(model.grid_import_mwh[sid, t]) - data.grid_import_capacity_mw * hours))
            if data.grid_export_capacity_mw is not None:
                export_limits.append(max(0.0, value(model.grid_export_mwh[sid, t]) - data.grid_export_capacity_mw * hours))
            for a in model.STORAGES:
                storage = storages[a]
                charge, discharge = value(model.charge_power_mw[sid, a, t]), value(model.discharge_power_mw[sid, a, t])
                inflow = natural_inflow(scenario, a, t, first_storage_id)
                spill = value(model.spilled_inflow_mwh[sid, a, t])
                expected = value(model.stored_energy_mwh[sid, a, t]) + storage.charge_efficiency * charge * hours - discharge * hours / storage.discharge_efficiency + inflow - spill
                transitions.append(abs(value(model.stored_energy_mwh[sid, a, t + 1]) - expected))
                spill_limits.append(max(0.0, spill - inflow))
                simultaneous.append(min(charge, discharge))
                if sid != reference and t < min(commitment_periods, data.number_of_periods):
                    nonanticipativity.extend([abs(charge-value(model.charge_power_mw[reference, a, t])), abs(discharge-value(model.discharge_power_mw[reference, a, t]))])
    maximum = max(balance + transitions + simultaneous + nonanticipativity + spill_limits + import_limits + export_limits, default=0)
    import_limit_mwh = None if data.grid_import_capacity_mw is None else data.grid_import_capacity_mw * hours
    export_limit_mwh = None if data.grid_export_capacity_mw is None else data.grid_export_capacity_mw * hours
    import_values = [value(model.grid_import_mwh[sid, t]) for sid in scenarios for t in range(data.number_of_periods)]
    export_values = [value(model.grid_export_mwh[sid, t]) for sid in scenarios for t in range(data.number_of_periods)]
    return {"solution_validated":maximum <= tolerance, "maximum_energy_balance_residual_mwh":max(balance, default=0), "maximum_storage_transition_residual_mwh":max(transitions, default=0), "maximum_simultaneous_charge_discharge_mw":max(simultaneous, default=0), "maximum_nonanticipativity_residual":max(nonanticipativity, default=0), "maximum_spill_limit_violation_mwh":max(spill_limits, default=0), "maximum_grid_import_limit_violation_mwh":max(import_limits, default=0), "maximum_grid_export_limit_violation_mwh":max(export_limits, default=0), "grid_import_binding_scenario_periods":0 if import_limit_mwh is None else sum(abs(item-import_limit_mwh) <= tolerance for item in import_values), "grid_export_binding_scenario_periods":0 if export_limit_mwh is None else sum(abs(item-export_limit_mwh) <= tolerance for item in export_values), "maximum_grid_import_utilization":None if not import_limit_mwh else max(import_values, default=0)/import_limit_mwh, "maximum_grid_export_utilization":None if not export_limit_mwh else max(export_values, default=0)/export_limit_mwh, "shared_commitment_periods":min(commitment_periods, data.number_of_periods), "storage_count":len(data.storages)}
