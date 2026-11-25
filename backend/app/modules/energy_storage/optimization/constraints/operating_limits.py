from pyomo.environ import Constraint


def add_operating_limit_constraints(model, data) -> None:
    """Apply reservoir, pump, turbine, and mutually exclusive operating limits."""
    storages = {storage.id: storage for storage in data.storages}

    def storage_minimum(m, a, t):
        return m.stored_energy_mwh[a, t] >= storages[a].minimum_energy_mwh

    def storage_maximum(m, a, t):
        return m.stored_energy_mwh[a, t] <= storages[a].energy_capacity_mwh

    def charge_limit(m, a, t):
        return m.charge_power_mw[a, t] <= storages[a].maximum_charge_power_mw * m.is_charging[a, t]

    def discharge_limit(m, a, t):
        return m.discharge_power_mw[a, t] <= storages[a].maximum_discharge_power_mw * (1 - m.is_charging[a, t])

    model.storage_minimum = Constraint(model.STORAGES, model.STATE_PERIODS, rule=storage_minimum)
    model.storage_maximum = Constraint(model.STORAGES, model.STATE_PERIODS, rule=storage_maximum)
    model.charge_power_limit = Constraint(model.STORAGES, model.PERIODS, rule=charge_limit)
    model.discharge_power_limit = Constraint(model.STORAGES, model.PERIODS, rule=discharge_limit)
    model.terminal_storage_requirement = Constraint(model.STORAGES, rule=lambda m, a: m.stored_energy_mwh[a, data.number_of_periods] >= storages[a].terminal_energy_minimum_mwh)

