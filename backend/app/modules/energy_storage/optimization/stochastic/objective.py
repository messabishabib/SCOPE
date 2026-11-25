from pyomo.environ import Expression, Objective, minimize

from .constraints import export_price, import_price


def define_expected_cost_objective(model, data, scenarios, probabilities) -> None:
    hours = data.interval_hours
    storages = {storage.id: storage for storage in data.storages}

    def scenario_cost(m, s):
        operations = sum(
            m.grid_import_mwh[s, t] * import_price(data, scenarios[s], t)
            - m.grid_export_mwh[s, t] * export_price(data, scenarios[s], t)
            + sum(m.charge_power_mw[s, a, t] * hours * storages[a].variable_charge_cost_per_mwh + m.discharge_power_mw[s, a, t] * hours * storages[a].variable_discharge_cost_per_mwh for a in m.STORAGES)
            + m.unserved_energy_mwh[s, t] * data.shortage_penalty_per_mwh
            + sum(m.spilled_inflow_mwh[s, a, t] for a in m.STORAGES) * data.spill_penalty_per_mwh
            for t in m.PERIODS)
        return operations - sum(m.stored_energy_mwh[s, a, data.number_of_periods] for a in m.STORAGES) * data.terminal_energy_value_per_mwh

    model.scenario_cost = Expression(model.SCENARIOS, rule=scenario_cost)
    model.expected_total_system_cost = Expression(expr=sum(probabilities[s] * model.scenario_cost[s] for s in model.SCENARIOS))
    model.minimize_expected_total_system_cost = Objective(expr=model.expected_total_system_cost, sense=minimize)

