from pyomo.environ import Constraint


def add_storage_dynamics_constraints(model, data) -> None:
    """Track stored energy after charging losses and discharge withdrawals."""
    storages = {storage.id: storage for storage in data.storages}
    hours = data.interval_hours
    model.initial_storage = Constraint(model.STORAGES, rule=lambda m, a: m.stored_energy_mwh[a, 0] == storages[a].initial_energy_mwh)

    def transition(m, a, t):
        storage = storages[a]
        charged = storage.charge_efficiency * m.charge_power_mw[a, t] * hours
        withdrawn = m.discharge_power_mw[a, t] * hours / storage.discharge_efficiency
        return m.stored_energy_mwh[a, t + 1] == m.stored_energy_mwh[a, t] + charged - withdrawn

    model.storage_transition = Constraint(model.STORAGES, model.PERIODS, rule=transition)

