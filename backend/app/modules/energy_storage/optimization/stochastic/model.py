from pyomo.environ import ConcreteModel, RangeSet, Set

from .constraints import add_energy_balance_constraints, add_nonanticipativity_constraints, add_operating_constraints, add_storage_constraints
from .objective import define_expected_cost_objective
from .variables import declare_decision_variables


def normalized_probabilities(scenarios):
    supplied = [s.probability for s in scenarios]
    weights = supplied if all(x is not None for x in supplied) and sum(supplied) > 0 else [1 / len(scenarios)] * len(scenarios)
    total = sum(weights)
    return {s.id: float(weights[i] / total) for i, s in enumerate(scenarios)}


def build_model(data, commitment_periods: int = 1):
    if len(data.scenarios) < 2:
        raise ValueError("Stochastic energy planning requires at least two scenarios")
    scenario_ids = [s.id for s in data.scenarios]
    scenarios = {s.id: s for s in data.scenarios}
    probabilities = normalized_probabilities(data.scenarios)
    model = ConcreteModel(name=f"stochastic_energy_storage_{data.id}")
    model.SCENARIOS = Set(initialize=scenario_ids)
    model.STORAGES = Set(initialize=[storage.id for storage in data.storages], ordered=True)
    model.PERIODS = RangeSet(0, data.number_of_periods - 1)
    model.STATE_PERIODS = RangeSet(0, data.number_of_periods)
    declare_decision_variables(model)
    add_energy_balance_constraints(model, data, scenarios)
    add_storage_constraints(model, data, scenarios)
    add_operating_constraints(model, data)
    add_nonanticipativity_constraints(model, scenario_ids, commitment_periods)
    define_expected_cost_objective(model, data, scenarios, probabilities)
    return model, scenarios, probabilities

