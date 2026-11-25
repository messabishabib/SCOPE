from pyomo.environ import Constraint, ConstraintList


def demand(data, scenario, t):
    return data.demand_mwh[t] * scenario.demand_multiplier[t]


def renewable(data, scenario, t):
    return data.renewable_generation_mwh[t] * scenario.renewable_multiplier[t]


def import_price(data, scenario, t):
    return data.grid_import_price_per_mwh[t] * scenario.price_multiplier[t]


def export_price(data, scenario, t):
    return data.grid_export_price_per_mwh[t] * scenario.price_multiplier[t]


def natural_inflow(scenario, storage_id, t, first_storage_id):
    if storage_id in scenario.natural_inflow_mwh_by_storage:
        return scenario.natural_inflow_mwh_by_storage[storage_id][t]
    return scenario.natural_inflow_mwh[t] if storage_id == first_storage_id else 0.0


def add_energy_balance_constraints(model, data, scenarios) -> None:
    hours = data.interval_hours

    def balance(m, s, t):
        scenario = scenarios[s]
        supply = renewable(data, scenario, t) - m.renewable_curtailment_mwh[s, t] + m.grid_import_mwh[s, t] + sum(m.discharge_power_mw[s, a, t] for a in m.STORAGES) * hours + m.unserved_energy_mwh[s, t]
        use = demand(data, scenario, t) + sum(m.charge_power_mw[s, a, t] for a in m.STORAGES) * hours + m.grid_export_mwh[s, t]
        return supply == use

    model.energy_balance = Constraint(model.SCENARIOS, model.PERIODS, rule=balance)
    model.renewable_curtailment_limit = Constraint(model.SCENARIOS, model.PERIODS, rule=lambda m, s, t: m.renewable_curtailment_mwh[s, t] <= renewable(data, scenarios[s], t))


def add_storage_constraints(model, data, scenarios) -> None:
    storages = {storage.id: storage for storage in data.storages}
    first_storage_id, hours = data.storages[0].id, data.interval_hours
    model.initial_storage = Constraint(model.SCENARIOS, model.STORAGES, rule=lambda m, s, a: m.stored_energy_mwh[s, a, 0] == storages[a].initial_energy_mwh)

    def transition(m, s, a, t):
        storage = storages[a]
        charged = storage.charge_efficiency * m.charge_power_mw[s, a, t] * hours
        withdrawn = m.discharge_power_mw[s, a, t] * hours / storage.discharge_efficiency
        return m.stored_energy_mwh[s, a, t + 1] == m.stored_energy_mwh[s, a, t] + charged - withdrawn + natural_inflow(scenarios[s], a, t, first_storage_id)

    model.storage_transition = Constraint(model.SCENARIOS, model.STORAGES, model.PERIODS, rule=transition)
    model.storage_minimum = Constraint(model.SCENARIOS, model.STORAGES, model.STATE_PERIODS, rule=lambda m, s, a, t: m.stored_energy_mwh[s, a, t] >= storages[a].minimum_energy_mwh)
    model.storage_maximum = Constraint(model.SCENARIOS, model.STORAGES, model.STATE_PERIODS, rule=lambda m, s, a, t: m.stored_energy_mwh[s, a, t] <= storages[a].energy_capacity_mwh)
    model.terminal_storage_requirement = Constraint(model.SCENARIOS, model.STORAGES, rule=lambda m, s, a: m.stored_energy_mwh[s, a, data.number_of_periods] >= storages[a].terminal_energy_minimum_mwh)


def add_operating_constraints(model, data) -> None:
    storages = {storage.id: storage for storage in data.storages}
    model.charge_power_limit = Constraint(model.SCENARIOS, model.STORAGES, model.PERIODS, rule=lambda m, s, a, t: m.charge_power_mw[s, a, t] <= storages[a].maximum_charge_power_mw * m.is_charging[s, a, t])
    model.discharge_power_limit = Constraint(model.SCENARIOS, model.STORAGES, model.PERIODS, rule=lambda m, s, a, t: m.discharge_power_mw[s, a, t] <= storages[a].maximum_discharge_power_mw * (1 - m.is_charging[s, a, t]))


def add_nonanticipativity_constraints(model, scenario_ids, commitment_periods: int) -> None:
    """Near-term physical actions must be selected before the scenario is revealed."""
    reference = scenario_ids[0]
    model.nonanticipativity = ConstraintList()
    for scenario_id in scenario_ids[1:]:
        for t in range(min(commitment_periods, len(model.PERIODS))):
            for storage_id in model.STORAGES:
                model.nonanticipativity.add(model.charge_power_mw[scenario_id, storage_id, t] == model.charge_power_mw[reference, storage_id, t])
                model.nonanticipativity.add(model.discharge_power_mw[scenario_id, storage_id, t] == model.discharge_power_mw[reference, storage_id, t])
                model.nonanticipativity.add(model.is_charging[scenario_id, storage_id, t] == model.is_charging[reference, storage_id, t])

