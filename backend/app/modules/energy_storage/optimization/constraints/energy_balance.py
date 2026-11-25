from pyomo.environ import Constraint


def add_energy_balance_constraints(model, data) -> None:
    """Supply plus unmet energy equals demand, pumping, and exports in each period."""
    hours = data.interval_hours

    def energy_balance(m, t):
        supply = data.renewable_generation_mwh[t] - m.renewable_curtailment_mwh[t] + m.grid_import_mwh[t] + sum(m.discharge_power_mw[a, t] for a in m.STORAGES) * hours + m.unserved_energy_mwh[t]
        use = data.demand_mwh[t] + sum(m.charge_power_mw[a, t] for a in m.STORAGES) * hours + m.grid_export_mwh[t]
        return supply == use

    model.energy_balance = Constraint(model.PERIODS, rule=energy_balance)
    model.renewable_curtailment_limit = Constraint(model.PERIODS, rule=lambda m, t: m.renewable_curtailment_mwh[t] <= data.renewable_generation_mwh[t])
    if data.grid_import_capacity_mw is not None:
        model.grid_import_limit = Constraint(model.PERIODS, rule=lambda m, t: m.grid_import_mwh[t] <= data.grid_import_capacity_mw * hours)
    if data.grid_export_capacity_mw is not None:
        model.grid_export_limit = Constraint(model.PERIODS, rule=lambda m, t: m.grid_export_mwh[t] <= data.grid_export_capacity_mw * hours)

