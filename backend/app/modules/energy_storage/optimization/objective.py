from pyomo.environ import Expression, Objective, minimize


def define_objective(model, data) -> None:
    """Build named cost components first, then the auditable total objective."""
    hours = data.interval_hours
    storages = {storage.id: storage for storage in data.storages}
    model.grid_import_cost = Expression(expr=sum(model.grid_import_mwh[t] * data.grid_import_price_per_mwh[t] for t in model.PERIODS))
    model.grid_export_revenue = Expression(expr=sum(model.grid_export_mwh[t] * data.grid_export_price_per_mwh[t] for t in model.PERIODS))
    model.charging_cost = Expression(expr=sum(model.charge_power_mw[a, t] * hours * storages[a].variable_charge_cost_per_mwh for a in model.STORAGES for t in model.PERIODS))
    model.discharging_cost = Expression(expr=sum(model.discharge_power_mw[a, t] * hours * storages[a].variable_discharge_cost_per_mwh for a in model.STORAGES for t in model.PERIODS))
    model.shortage_cost = Expression(expr=sum(model.unserved_energy_mwh[t] * data.shortage_penalty_per_mwh for t in model.PERIODS))
    model.terminal_storage_value = Expression(expr=sum(model.stored_energy_mwh[a, data.number_of_periods] for a in model.STORAGES) * data.terminal_energy_value_per_mwh)
    model.total_system_cost = Expression(expr=model.grid_import_cost - model.grid_export_revenue + model.charging_cost + model.discharging_cost + model.shortage_cost - model.terminal_storage_value)
    model.minimize_total_system_cost = Objective(expr=model.total_system_cost, sense=minimize)

